#!/usr/bin/python -Es
# Copyright (C) 2016 Red Hat
# AUTHOR: Giuseppe Scrivano <gscrivan@redhat.com>

#    This program is free software; you can redistribute it and/or
#    modify it under the terms of the GNU General Public License as
#    published by the Free Software Foundation; either version 2 of
#    the License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#    02110-1301 USA.

import libtorrent as torrent # rb_libtorrent-python2
import BaseHTTPServer, SimpleHTTPServer
import ssl
import httplib
import hashlib
import os
import urllib2
import shutil
import etcd # python2-python-etcd.noarch
import sys
import socket
import base64
import subprocess

torrent_session = None
etcd_client = None

def fsync(directory):
    with open("/dev/null", "rw") as DEVNULL:
        subprocess.check_call(["sync", "--file-system", directory], stdin=DEVNULL,
                              stdout=DEVNULL,
                              stderr=DEVNULL)

def add_torrent(f):
    ti = torrent.torrent_info(f)
    h = torrent_session.add_torrent({'ti': ti,
                                     'save_path' : "storage/blobs",
                                     'seed_mode': True})
    info = torrent.torrent_info(f)
    key = "/torrents/" + os.path.basename(f).replace(".torrent", "")
    with open(f, "r") as content:
        t = content.read()
    print("Add torrent %s -> %s" % (key, f))
    etcd_client.write(key, base64.b64encode(t))

def create_torrent(blob, path):
    destination = os.path.join("storage/torrents", blob + ".torrent")
    if os.path.exists(destination):
        return destination
    fs = torrent.file_storage()
    torrent.add_files(fs, path)
    t = torrent.create_torrent(fs)
    t.add_tracker(TRACKER, 0)
    t.set_comment(blob)
    torrent.set_piece_hashes(t, os.path.dirname(path))
    generated_torrent = t.generate()
    with open(destination, "wb") as f:
        f.write(torrent.bencode(generated_torrent))

    add_torrent(destination)
    return destination

def try_torrent(checksum):
    key = "/torrents/" + checksum
    try:
        value = etcd_client.get(key).value
        torrent_file = base64.b64decode(value)
    except etcd.EtcdKeyNotFound:
        print("Torrent for %s not found" % checksum)
        return None
    except etcd.EtcdConnectionFailed:
        print("Failed to connect to the etcd server, giving up on torrent")
        return None

    tmp_torrent = os.path.join("storage/tmp", checksum + ".torrent")
    dst_torrent = os.path.join("storage/torrents", checksum + ".torrent")
    for i in [tmp_torrent, dst_torrent]:
        if not os.path.exists(i):
            os.makedirs(i)

    with open(tmp_torrent, "wb") as f:
        f.write(torrent_file)
    ti = torrent.torrent_info(tmp_torrent)
    handle = torrent_session.add_torrent({'ti': ti,
                                          'save_path' : "storage/tmp/",
                                          'seed_mode': False})

    wait = 0
    while handle.status().state != torrent.torrent_status.seeding:
        import time
        time.sleep(1)
        if wait > 3 and (handle.status().num_complete <= 0 or handle.status().progress < 0.001):
            print("nothing happened, give up")
            return None
        wait = wait + 1
        print('%d%% done' % (handle.status().progress * 100))

    src = os.path.join("storage/tmp", checksum)
    dst = os.path.join("storage/blobs", checksum)
    fsync("storage/tmp")
    shutil.move(src, dst)
    shutil.move(tmp_torrent, dst_torrent)
    fsync("storage/blobs")
    fsync("storage/torrents")

    torrent_session.remove_torrent(handle)

    add_torrent(dst_torrent)
    return dst

class MirrorHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def do_GET(self):
        return self.get_location(self.path)

    def setup(self):
        self.connection = self.request
        self.rfile = socket._fileobject(self.request, "rb", self.rbufsize)
        self.wfile = socket._fileobject(self.request, "wb", self.wbufsize)

    def get_location(self, destination_url, is_registry=True, blob_name=None):
        original_host = self.headers.getheader("Host")
        # for a docker blob, try the torrent only if there is an Authorization header in the request
        is_docker_blob = "/blobs/" in destination_url and "authorization" in self.headers
        # for an ostree blob, try the torrent only for deltas, except the superblock file
        is_ostree_blob = "/deltas/" in destination_url and not "superblock" in destination_url

        send_file = None
        if destination_url.startswith("http://") or destination_url.startswith("https://"):
            is_registry = False

        if blob_name is None:
            if is_docker_blob:
                blob_name = destination_url[destination_url.rfind("sha256:"):]
            elif is_ostree_blob:
                blob_name = destination_url[destination_url.rfind("/deltas/")+8:].replace('/', "")

        if is_docker_blob or is_ostree_blob:
            stored_file = os.path.join("storage/blobs/", blob_name)
            if os.path.exists(stored_file):
                send_file = stored_file
            else:
                send_file = try_torrent(blob_name)

            if not send_file:
                hash_res = hashlib.sha256()

        if send_file:
            size = os.stat(send_file).st_size
            self.send_response(200)
            headers = {'content-type': 'application/octet-stream',
                       'content-length': str(size),
                       'connection' : 'close',
                       'docker-distribution-api-version': 'registry/2.0',
                       'docker-content-digest': blob_name,
                       'accept-ranges': "bytes"}
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()

            with open(send_file, "rb") as f:
                written = 0
                while written < size:
                    data = f.read(1 << 20)
                    if len(data) == 0:
                        break
                    written += len(data)
                    self.wfile.write(data)
                    self.wfile.flush()
            return
        elif not is_registry:
            res = None
            try:
                res = urllib2.urlopen(destination_url)
            except urllib2.HTTPError as e:
                res_code = e.code

            headers = {}
            if res:
                res_code = res.getcode()
                for k in res.headers:
                    headers[k.lower()] = res.headers[k]
        else:
            try:
                req_headers = {}
                for k in self.headers:
                    val = self.headers.get(k)
                    if original_host in val.lower():
                        val = val.lower().replace(original_host, REGISTRY_LOCATION)
                    req_headers[k] = val

                host, port = REGISTRY_LOCATION.split(':') if ':' in REGISTRY_LOCATION else (REGISTRY_LOCATION, 443)
                registry_conn = httplib.HTTPSConnection(host, port)

                registry_conn.request('GET', destination_url, headers=req_headers)
                res = registry_conn.getresponse()
                res_code = res.status
                headers = {}
                for k, v in res.getheaders():
                    headers[k] = v
            except httplib.HTTPException, e:
                res_code = e.code

        # if Location is present, resolve it internally.
        if is_docker_blob and "location" in headers:
            location = headers["location"]
            self.get_location(location, is_registry=False, blob_name=blob_name)
            return

        self.send_response(res_code)
        for k, v in headers.items():
            if REGISTRY_LOCATION in v.lower():
                v = v.lower().replace(REGISTRY_LOCATION, original_host)

            # Do not set these headers
            if k.lower() in ["transfer-encoding"]:
                continue

            self.send_header(k, v)
        self.end_headers()

        if not res:
            return

        f = open(os.path.join("storage/tmp", blob_name), "w") if (is_docker_blob or is_ostree_blob) else None
        try:
            # Handle the payload here
            while True:
                data = res.read()
                if len(data) == 0:
                    break
                if f:
                    f.write(data)
                self.wfile.write(data)
                if is_docker_blob:
                    hash_res.update(data)
        finally:
            if is_docker_blob or is_ostree_blob:
                f.close()
                move_torrent = hash_res.hexdigest() == blob_name.replace("sha256:", "") or is_ostree_blob
                if move_torrent:
                     shutil.move(os.path.join("storage/tmp", blob_name), os.path.join("storage/blobs", blob_name))
                     create_torrent(blob_name, os.path.join("storage/blobs", blob_name))

if __name__ == '__main__':
    for i in ["storage/tmp", "storage/torrents", "storage/blobs"]:
        try:
            os.makedirs(i)
        except OSError:
            pass

    PORT = int(os.environ.get("PORT", "8888"))
    INTERFACE = os.environ.get("INTERFACE", "0.0.0.0")
    REGISTRY_NO_SSL = os.environ.get("REGISTRY_NO_SSL", False)
    REGISTRY_LOCATION = os.environ.get("REGISTRY_LOCATION", 'registry-1.docker.io')
    TRACKER = os.environ.get("TRACKER", 'http://192.168.1.1:6969/announce')
    ETCD_HOST = os.environ.get("ETCD_HOST", '192.168.1.1')
    ETCD_PORT = int(os.environ.get("ETCD_PORT", '2378'))
    TORRENT_FIRST_PORT = int(os.environ.get("TORRENT_FIRST_PORT", '6881'))
    TORRENT_LAST_PORT = int(os.environ.get("TORRENT_LAST_PORT", '6891'))
    CERTFILE = os.environ.get("CERTFILE", '/etc/torrent-proxy/ssl/cert.pem')
    PRIVATEKEY = os.environ.get("PRIVATEKEY", '/etc/torrent-proxy/ssl/key.pem')

    etcd_client = etcd.Client(host=ETCD_HOST, port=ETCD_PORT)

    torrent_session = torrent.session()
    torrent_session.listen_on(TORRENT_FIRST_PORT, TORRENT_LAST_PORT)
    if not os.path.exists("storage/torrents"):
        os.makedirs("storage/torrents")
    for f in os.listdir("storage/torrents"):
        add_torrent(os.path.join("storage/torrents", f))

    print("Listen on port %i" % PORT)
    httpd = BaseHTTPServer.HTTPServer((INTERFACE, PORT), MirrorHandler)
    if not REGISTRY_NO_SSL:
        httpd.socket = ssl.wrap_socket(httpd.socket, keyfile=PRIVATEKEY, certfile=CERTFILE, server_side=True)
    print("Ready")
    httpd.serve_forever()

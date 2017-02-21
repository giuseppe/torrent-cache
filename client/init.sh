#!/bin/sh
test -e /etc/torrent-proxy/ssl/key.pem || /generate.sh

exec /torrent_proxy.py

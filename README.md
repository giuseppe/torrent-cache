torrent-cache
===============

*Disclaimer: It is a proof of concept and should not be used in production.*

HTTP(S) proxy that uses BitTorrent to fetch Docker blobs and OSTree
static deltas on a local network.

This software is made of two components, both of them run in a Docker container.

The `client` should run locally on each host and use it as a proxy for
`OSTree` and `Docker` updates, some [examples](#examples) are provided at the
bottom.

Both containers have a volume for their storage on `/storage`, so
bind mount it to something reasonable.

## `tracker`
It runs OpenTracker to track the available torrents and an etcd
server.  The OpenTracker server is used to track what torrents are
currently available and what `clients` have them.  Etcd is used to store
the `.torrent` files and to serve them to the clients.
The OpenTracker listens on any network interface and allows everyone
to register new torrents.  This can pose security issues.  Be aware of
it!

## `client`
Designed to run locally and serve as a proxy for Docker/OSTree.  When
a request for a Docker image blob or an OSTree static delta file is
received, the client contacts the Etcd server for the `.torrent` file,
if it is found then it tries to contact other clients (through the
tracker) to download it.
If it is not found, then it is downloaded from the registry, a
`.torrent` is created and registered on the `tracker`.

A `tracker` host is required for a network.  This is where all the
clients will connect to.  The `tracker` can be created as:

`docker run -v /var/lib/torrent-tracker:/storage --rm -it -p 2378:2378 -p 6969:6969 tracker`

The client accepts a bunch of environment variables for its
configuration. Some of them are mostly useful when not running in a
container:

-`PORT` what port it is listening on (default: 8888)

-`INTERFACE` interface it is listening on (default: 0.0.0.0)

-`REGISTRY_NO_SSL` if set, the proxy will use HTTP. (default: not set)

-`REGISTRY_LOCATION` upstream registry location (default: registry-1.docker.io)

-`TRACKER`  tracker address (default: http://192.168.1.1:6969/announce)

-`ETCD_HOST` etcd server (default: 192.168.1.1)

-`ETCD_PORT` etcd server port (default: 2378)

-`TORRENT_FIRST_PORT` first port listening on for Torrents (default: 6881)

-`TORRENT_LAST_PORT` last port listening on for Torrent (default: 6891)

-`CERTFILE` path to the certificate file for the HTTPS server (default: /etc/torrent-proxy/ssl/cert.pem)

-`PRIVATEKEY` path to the private key (default: /etc/torrent-proxy/ssl/key.pem)

# Examples

For creating a `client`, assuming the `TRACKER` and the `ETCD_HOST` have
different values than the default:

`docker run -it -v /var/lib/torrent-storage:/storage -e TRACKER=http://192.168.1.1:6969/announce -e ETCD_HOST=192.168.1.1 -p 8888:8888 -p 6881-6891 --rm client`

To use it from OSTree, it is enough to use it as a proxy, like:

`http_proxy=http://localhost:8888 ostree --repo=repo pull origin test`

For Docker, you can set it up as an alternate mirror.  Add this configuration is passed to the Docker daemon and restart it:

`--registry-mirror=https://localhost:8888`

For a test you can try to fetch an image via Skopeo as:

`skopeo --tls-verify=false layers docker://localhost:8888/library/fedora`

# Improvements

- Use a real HTTP proxy instead of the Python hack implementation.

- Use DHT instead of requiring an OpenTracker.

- Use a single torrent file for an OSTree delta.

- The proxy container should be able to share storage with OSTree on
  the host, and possibly Docker, so we don't require extra storage.

- Keep local torrents in sync with the images currently available.

- Alternatively, implement a way to remove old/unused torrents.

#!/bin/sh
mkdir -p /etc/torrent-proxy/ssl
cd /etc/torrent-proxy/ssl
openssl req -x509 -newkey rsa:4096 -subj "/C=US/CN=localhost" -keyout key.pem -nodes -out cert.pem -days 10000

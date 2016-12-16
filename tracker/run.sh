#!/bin/sh
etcd --listen-client-urls 'http://0.0.0.0:2378' --advertise-client-urls="http://0.0.0.0:2378" &

/opentracker

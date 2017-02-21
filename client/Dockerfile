FROM fedora

LABEL Summary="A local proxy for mapping HTTP requests to BitTorrent" \
      Maintainer="Giuseppe Scrivano <gscrivan@redhat.com>"

RUN dnf install -y python2 python2-urllib3 openssl rb_libtorrent-python2 python2-python-etcd
ADD init.sh generate-key.sh torrent_proxy.py /
RUN mkdir -p /etc/torrent-proxy/ssl

EXPOSE 8888
EXPOSE 6881-6891
VOLUME /storage

COPY system-container/manifest.json system-container/config.json.template system-container/service.template system-container/tmpfiles.template /exports/

CMD /init.sh

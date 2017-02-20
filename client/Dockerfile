FROM fedora

LABEL Summary="A local proxy for mapping HTTP requests to BitTorrent" \
      Maintainer="Giuseppe Scrivano <gscrivan@redhat.com>"

RUN dnf install -y python2 python2-urllib3 openssl rb_libtorrent-python2 python2-python-etcd
ADD generate-key.sh torrent_proxy.py /
RUN /generate-key.sh

EXPOSE 8888
EXPOSE 6881-6891
VOLUME /storage

CMD /torrent_proxy.py


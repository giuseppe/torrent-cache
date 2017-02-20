FROM fedora

LABEL Summary="An open tracker for BitTorrents" \
      Maintainer="Giuseppe Scrivano <gscrivan@redhat.com>"

RUN dnf install -y make zlib-devel libowfat-devel git gcc etcd && dnf clean all && mkdir /root/opentracker
ADD run.sh build.sh /root/opentracker/
RUN cd /root/opentracker && ./build.sh

EXPOSE 2378
EXPOSE 6969

CMD /root/opentracker/run.sh


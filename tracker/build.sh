#!/bin/sh

git clone git://erdgeist.org/opentracker
cd opentracker

echo "FEATURES+=-DWANT_ACCESSLIST_BLACK" > Makefile.new
echo "LIBOWFAT_HEADERS=/usr/include/libowfat" >> Makefile.new
echo "LIBOWFAT_LIBRARY=/usr/lib64/" >> Makefile.new
cat Makefile | grep -v ^LIBOWFAT >> Makefile.new
make -f Makefile.new

cp opentracker /

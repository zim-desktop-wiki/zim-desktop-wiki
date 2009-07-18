#!/bin/sh
grep -Rc FIXME\\\|TODO zim tests | \
	grep \\.py: | \
	perl -pe 's/^(.*):(.*)/$2 $1/' | \
	sort -n | \
	grep -v ^0

#!/bin/sh

P='tests/data/formats'

cat $P/wiki.txt | python -m zim.formats wiki > $P/parsetree.xml
cat $P/wiki.txt | python -m zim.formats wiki plain $P > $P/plain.txt
cat $P/wiki.txt | python -m zim.formats wiki html $P > $P/export.html
cat $P/wiki.txt | python -m zim.formats wiki latex $P > $P/export.tex
cat $P/wiki.txt | python -m zim.formats wiki markdown $P > $P/export.markdown
cat $P/wiki.txt | python -m zim.formats wiki rst $P > $P/export.rst

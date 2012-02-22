#!/bin/sh

P='tests/data/formats'

cat $P/wiki.txt | python -m zim.formats wiki > $P/parsetree.xml
cat $P/wiki.txt | python -m zim.formats wiki plain > $P/plain.txt
cat $P/wiki.txt | python -m zim.formats wiki html > $P/export.html
cat $P/wiki.txt | python -m zim.formats wiki latex > $P/export.tex
cat $P/wiki.txt | python -m zim.formats wiki markdown > $P/export.markdown

#!/bin/sh

./zim.py --export ./website/ -V \
	--template ./website/template.html \
	--output ./html/

./zim.py --export ./data/manual/ -V \
	--template ./website/template.html \
	--output ./html/manual/

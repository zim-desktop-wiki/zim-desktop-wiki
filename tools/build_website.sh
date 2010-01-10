#!/bin/sh

rm -fr './html'

./zim.py --export ./website/pages/ -V \
	--template ./website/template.html \
	--output ./html/ \
	--root-url /

./zim.py --export ./data/manual/ -V \
	--template ./website/template.html \
	--output ./html/manual/ \
	--root-url /

cp -R website/files/* html/

perl -i -pe 's{INSERT_SCREENCAST_HERE}{<object width="480" height="385"><param name="movie" value="http://www.youtube.com/v/yBZpWgzO9Ps&hl=en_US&fs=1&rel=0&color1=0x3a3a3a&color2=0x999999"></param><param name="allowFullScreen" value="true"></param><param name="allowscriptaccess" value="always"></param><embed src="http://www.youtube.com/v/yBZpWgzO9Ps&hl=en_US&fs=1&rel=0&color1=0x3a3a3a&color2=0x999999" type="application/x-shockwave-flash" allowscriptaccess="always" allowfullscreen="true" width="480" height="385"></embed></object>}' html/screenshots.html

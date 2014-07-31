#!/bin/sh

rm -fr './html'

./zim.py --index ./website/pages/ -V
./zim.py --export ./website/pages/ -V \
	--template ./website/template.html \
	--output ./html/ \
	--root-url /

./zim.py --index ./data/manual/ -V
./zim.py --export ./data/manual/ -V \
	--template ./website/template.html \
	--output ./html/manual/ \
	--root-url /

cp -R website/files/* html/

# HACKs to include raw HTML
perl -i -pe 's{INSERT_SCREENCAST_HERE}{<object width="480" height="385"><param name="movie" value="http://www.youtube.com/v/yBZpWgzO9Ps&hl=en_US&fs=1&rel=0&color1=0x3a3a3a&color2=0x999999"></param><param name="allowFullScreen" value="true"></param><param name="allowscriptaccess" value="always"></param><embed src="http://www.youtube.com/v/yBZpWgzO9Ps&hl=en_US&fs=1&rel=0&color1=0x3a3a3a&color2=0x999999" type="application/x-shockwave-flash" allowscriptaccess="always" allowfullscreen="true" width="480" height="385"></embed></object>}' html/screenshots.html

perl -i -pe 's{INSERT_PAYPAL_BUTTON_HERE}{<form action="https://www.paypal.com/cgi-bin/webscr" method="post">
<input type="hidden" name="cmd" value="_s-xclick">
<input type="hidden" name="hosted_button_id" value="11297015">
<input type="image" src="https://www.paypal.com/en_US/i/btn/btn_donateCC_LG.gif" border="0" name="submit" alt="PayPal - The safer, easier way to pay online!">
<img alt="" border="0" src="https://www.paypal.com/nl_NL/i/scr/pixel.gif" width="1" height="1">
</form>}' html/contribute.html

perl -i -pe 's{http://www.zim-wiki.org/wiki/doku.php%3Fid%3D}{http://www.zim-wiki.org/wiki/doku.php?id=}'  html/contribute.html


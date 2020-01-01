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

# HACKs to include raw HTML
perl -i -pe 's{INSERT_PAYPAL_BUTTON_HERE}{<form action="https://www.paypal.com/cgi-bin/webscr" method="post">
<input type="hidden" name="cmd" value="_s-xclick">
<input type="hidden" name="hosted_button_id" value="11297015">
<input type="image" src="https://www.paypal.com/en_US/i/btn/btn_donateCC_LG.gif" border="0" name="submit" alt="PayPal - The safer, easier way to pay online!">
<img alt="" border="0" src="https://www.paypal.com/nl_NL/i/scr/pixel.gif" width="1" height="1">
</form>}' html/contribute.html

perl -i -pe 's{INSERT_REPOLOGY_BADGE_HERE}{<a href="https://repology.org/project/zim/versions">
    <img src="https://repology.org/badge/tiny-repos/zim.svg" alt="Packaging status">
</a>}' html/downloads.html

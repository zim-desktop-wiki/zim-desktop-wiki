#!/usr/bin/python3

import os
import glob
import subprocess

os.chdir('./data/icons/hicolor')

for svg in glob.glob('scalable/*-symbolic.svg'):
	for size in ('16x16', '22x22', '24x24'):
		png = size + '/actions/' + os.path.basename(svg)[:-4] + '.png'
		print(svg, '->', png)
		folder = os.path.dirname(png)
		subprocess.check_call(
			['gtk-encode-symbolic-svg', '-o', folder, svg, size])

# TODO: For non symbolic can use ImageMagick based command:
# png = size + '/actions/' + os.path.basename(svg)[:-4] + '.png'
# ['convert', '+antialias', '-background', 'transparent', '-resize', size, svg, png])

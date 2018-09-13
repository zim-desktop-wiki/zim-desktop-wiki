#!/usr/bin/python3

import sys
import os

if len(sys.argv) != 5:
	print('Usage: %s directory width depth random_links' % sys.argv[0])
	sys.exit(1)

root, width, depth, links = sys.argv[1:]
width = int(width)
depth = int(depth)
n_links = int(links)

assert not os.path.exists(root), 'Need new directory'

name = 'some_page_%i_%i'
content = '''\
Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.26

====== {title} ======
//Some test data//

Foooo Bar!

{links}
'''
content += ('la la laaa' * 20 + '\n') * 10


import random

def random_links(depth):
	links = []
	for n in range(random.randint(0, n_links)):
		links.append("[[%s]]\n" % random_name(depth))
	return ''.join(links)


def random_name(depth):
	i = random.randint(0, width)
	return name % (depth, i)


def populate_level(path, j):
    path += os.path.sep
    os.mkdir(path)
    d = 1

    for i in range(width):
        myname = name % (j, i)

        file = path + myname + '.txt'
        print('>', file)
        fh = open(file, 'w')
        fh.write(content.format(
			title=myname,
			links=random_links(j)
		))
        fh.close()

        if j < depth:
            d += populate_level(path + myname, j + 1)

    return d

d = populate_level(root, 0)
f = d * width

print('Total %i files %i directories' % (f, d))
print('Done')

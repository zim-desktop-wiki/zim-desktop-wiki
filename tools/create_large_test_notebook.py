#!/usr/bin/python3

import sys
import os
import random

if len(sys.argv) != 2:
	sys.exit("Usage: {} DIRECTORY".format(sys.argv[0]))

root = sys.argv[1]
assert not os.path.exists(root), 'Need new directory'

width = 25
depth = 2
n_links = 3


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


def random_links(my_depth):
	links = []

	for n in range(random.randint(0, n_links)):
		links.append("[[%s]]\n" % random_name(my_depth))

	if my_depth < depth:
		for n in range(random.randint(0, n_links)):
			links.append("[[+%s]]\n" % random_name(my_depth+1))
	else:
		for n in range(random.randint(0, n_links)):
			links.append("[[%s]]\n" % random_name(my_depth-1))

	for n in range(random.randint(0, n_links)):
		links.append("[[%s]]\n" % random_date_page())

	return ''.join(links)


def random_name(depth):
	i = random.randint(1, width)
	return name % (depth, i)


def random_date_page():
	year = 2010 + random.randint(0, 8)
	month = random.randint(1, 12)
	day = random.randint(1, 30)
	return ":Date:%i:%i:%i" % (year, month, day)


def populate_level(path, j):
	path += os.path.sep
	os.mkdir(path)
	d = 1

	for i in range(1, width+1):
		myname = name % (j, i)

		filename = os.path.join(path, "{}.txt".format(myname))
		print(">", filename)
		with open(filename, "w") as notebook:
			notebook.write(
				content.format(
					title=myname,
					links=random_links(j),
					# links=''
				)
			)

		if j < depth:
			d += populate_level(path + myname, j + 1)

	return d


d = populate_level(root, 0)
f = d * width

print("Total {} files {} directories".format(f, d))
print("Done")

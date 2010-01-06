#!/usr/bin/python

import sys
import os

if len(sys.argv) != 4:
	print 'Usage: %s directory with depth' % sys.argv[0]
	sys.exit(1)

root, width, depth = sys.argv[1:]
width = int(width)
depth = int(depth)

assert not os.path.exists(root), 'Need new directory'

name = 'some_page_%i_%i'
content = '''\
Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.26

====== Some Page ======
//Some test data//

Foooo Bar!

TODO: insert random links here
'''
content += ('la la laaa'*20 + '\n') * 10

def populate_level(path, j):
    path += os.path.sep
    os.mkdir(path)
    d = 1
    
    for i in range(width):
        myname = name % (j, i)
        
        file = path + myname + '.txt'
        print '>', file
        fh = open(file, 'w')
        fh.write(content)
        fh.close()
        
        if j < depth:
            d += populate_level(path + myname, j+1)

    return d

d = populate_level(root, 0)
f = d * width

print 'Total %i files %i directories' % (f, d)
print 'Done'

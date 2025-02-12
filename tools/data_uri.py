#!/usr/bin/python3

import base64
import sys

from zim.gui.applications import get_mimetype
from zim.newfs import LocalFile


def data_uri(file):
	mimetype = get_mimetype(file)
	data64 = base64.b64encode(file.read_binary()).decode('utf-8')
	return f'data:{mimetype};base64,{data64}'


def main():
	file = LocalFile(sys.argv[1])
	assert file.exists(), f'File \'{file}\' does not exist'
	print(data_uri(file))


if __name__ == '__main__':
	main()

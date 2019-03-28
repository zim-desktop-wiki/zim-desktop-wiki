#!/usr/bin/python3

import os
import subprocess

from http.server import HTTPServer
from http.server import SimpleHTTPRequestHandler

subprocess.call('./tools/build_website.sh')

os.chdir('./html')

try:
	server = HTTPServer(('', 8080), SimpleHTTPRequestHandler)
	print('server started at http://localhost:8080')
	server.serve_forever()
except KeyboardInterrupt:
	server.socket.close()

#!/usr/bin/python

import re

source_files = {}

comment_re = re.compile(r'\s+#\s+T:\s+(.+)\s*$')

def get_file(file):
	if not file in source_files:
		#~ print 'Extracting comments from', file
		source_files[file] = open(file).readlines()
		source_files[file].append('')
	return source_files[file]

def extract_comment(file, line):
	lines = get_file(file)
	line -= 1 # list is 0 based
	match = comment_re.search(lines[line])
	if match:
		# comment on same line
		return match.group(1)
	else:
		# search next line(s) for a comment
		i = line+1
		while i < len(lines):
			if '_(' in lines[i] or 'gettext(' in lines[i]:
				break
			else:
				match = comment_re.search(lines[i])
				if match:
					return match.group(1)
			i += 1
		return None

def extract_comments(sources):
	sources = [s.split(':') for s in sources]
	comments = []
	for file, line in sources:
		comment = extract_comment(file, int(line))
		if comment and comment not in comments:
			comments.append(comment)
	if comments:
		return ' | \n'.join(['#. '+c for c in comments])+'\n'
	else:
		print 'No translator comment for:'
		for file, line in sources:
			print '\t%s line %s' % (file, line)
		return ''

def add_comments(file):
	messages = open(file).readlines()
	fh = open(file, 'w')

	while messages:
		line = messages.pop(0)
		if line.startswith('#: '):
			lines = [line]
			sources = line[3:].strip().split()
			while messages[0].startswith('#: '):
				line = messages.pop(0)
				lines.append(line)
				sources += line[3:].strip().split()
			fh.write(extract_comments(sources))
			fh.writelines(lines)
		elif line.startswith('#. '):
			pass
		else:
			fh.write(line)

if __name__ == '__main__':
	add_comments('translations/zim.pot')

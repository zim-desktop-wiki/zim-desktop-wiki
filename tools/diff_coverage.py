#!/usr/bin/python3

# Tool that reads diff from pipe and filters out sections that are
# covered by testing
#
# Assumes code is new, after diff is applied

import coverage



class Diff(object):

	def __init__(self, lines=None):
		self.parts = []
		if lines:
			for part in self._readparts(lines):
				self.parts.append(part)

	def to_text(self):
		text = []
		for part in self.parts:
			text += ["==== ", part.file, "\n"]
			text += [part.head]
			text += part.lines
			text += ['\n']
		return ''.join(text)

	@staticmethod
	def _readparts(lines):
		lines = iter(lines)
		file = None
		for line in lines:
			if line.startswith('+++ '):
				file = line[4:].split()[0]
				if file.startswith('b/'):
					file = file[2:] # git has a/ b/ prefixes for old and new file
			elif line.startswith('@@'):
				assert file is not None
				head = line
				part = []
				for line in lines:
					if not line[0] in (' ', '+', '-'):
						break
					else:
						part.append(line)
				yield DiffPart(file, head, part)
			else:
				pass # any other line with info, not part of a diff block


class DiffPart(object):

	def __init__(self, file, head, lines):
		self.file = file
		self.head = head
		self.lines = lines

	def range(self):
		old, new = self.head.strip().split()[:2]
		start, size = list(map(int, new[1:].split(',')))
		return start, start + size



def coverage_filter_diff(diff):
	cov = coverage.coverage()
	cov.load()

	new = Diff()
	for part in diff.parts:
		if  part.file.startswith('zim') \
		and part.file.endswith('.py'):
			if not part_covered(part, cov):
				new.parts.append(part)
			else:
				print("Covered %s %s" % (part.file, part.head.strip()))
		else:
			print("Skip %s" % part.file)
	return new


def part_covered(part, cov):
	f, l, missing, r = cov.analysis(part.file)
	start, end = part.range()
	return not any(l >= start and l <= end for l in missing)


if __name__ == '__main__':
	import sys
	lines = sys.stdin.readlines()
	diff = Diff(lines)
	print("TODO: check timestamps diff vs timestamp './coverage'")
	diff = coverage_filter_diff(diff)
	sys.stdout.write(diff.to_text())

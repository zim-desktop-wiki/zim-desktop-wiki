#!/usr/bin/python

import os

class TextTree(object):

	def tostring(self, object):
		strings = self.tostrings(object)
		return ''.join(strings)

	def tostrings(self, object):
		strings = [object.name + '\n']

		def add_item(item, ps1, ps2):
			if isinstance(item, basestring):
				strings.append(ps1 + item + '\n')
			else:
				substrings = self.tostrings(item) # recurs
				strings.append(ps1 + substrings.pop(0))
				strings.extend([ps2 + s for s in substrings])

		items = object.items()
		if items:
			for i in range(len(items)-1):
				add_item(items[i], '|-- ', '|   ')
			add_item(items[-1], '`-- ', '    ')

		return strings



class ModuleFile(object):

	def __init__(self, file):
		assert os.path.isfile(file), 'Could not find file: %s' % file
		self.file = file
		self.name = os.path.basename(file)[:-3]

		self.classes = []
		for line in open(self.file):
			line = line.strip()
			if line.startswith('class') and line.endswith(':'):
				self.classes.append(line[5:-1].strip())

	def items(self):
		return self.classes[:]


class ModuleDir(ModuleFile):

	def __init__(self, dir):
		assert os.path.isdir(dir), 'Could not find dir: %s' % dir
		ModuleFile.__init__(self, dir+'/__init__.py')
		self.dir = dir
		self.name = os.path.basename(dir)
		self.modules = []

		paths = [dir+'/'+p for p in os.listdir(dir) if not p.startswith('_')]
		for file in [f for f in paths if f.endswith('.py')]:
			self.modules.append(ModuleFile(file))
		for subdir in [d for d in paths if os.path.isdir(d)]:
			self.modules.append(ModuleDir(subdir))

		self.modules.sort(key=lambda m: m.name)

	def items(self):
		items = ModuleFile.items(self)
		items.extend(self.modules)
		return items


if __name__ == '__main__':
	dir = ModuleDir('./zim')
	print TextTree().tostring(dir)

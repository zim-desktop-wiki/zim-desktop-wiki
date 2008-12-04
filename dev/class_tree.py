
import os

modules = {}

def find_classes(file):
	classes = []
	if file.endswith('__init__.py'):
		module = file[:-12].replace('/', '.')
	else:
		module = file[:-3].replace('/', '.')
	for line in open(file):
		line = line.strip()
		if line.startswith('class') and line.endswith(':'):
			classes.append(line[5:-1].strip())
	modules[module] = classes

for dir, dirs, files in os.walk('zim'):
	if '/_' in dir: 
		continue # skip zim/_lib 
	files = [f for f in files if f.endswith('.py')
			and (f == '__init__.py' or not f.startswith('_'))]
	for file in files:
		find_classes(dir+'/'+file)

tree = {}
for module in modules.keys():
	path = module.split('.')
	branch = tree
	for part in path:
		if part not in branch:
			branch[part] = {}
		branch = branch[part]

def print_module(module, branch, prefix):
	children = branch.keys()
	children.sort()
	if module in modules:
		classes = modules[module]
		for i in range(len(classes)-1):
			print prefix+'|-- %s' % classes[i]
		if children:
			print prefix+'|-- %s' % classes[-1]
		else:
			print prefix+'`-- %s' % classes[-1]
	if children:
		for i in range(len(children)-1):
			child = children[i]
			print prefix+'|-- %s' % child
			print_module(
				module+'.'+child, 
				branch[child], 
				prefix+'|   '
			)
		child = children[-1]
		print prefix+'`-- %s' % child
		print_module(
			module+'.'+child, 
			branch[child], 
			prefix+'    '
		)

for module in tree.keys():
	print module
	print_module(module, tree[module], '')


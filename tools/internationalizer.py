#!/usr/bin/python3

from gi.repository import Gtk
import tokenize
import token
import re

def match_ignore(string):
	if string.startswith("'''"):
		return True # ignore docstring etc.
	
	string = string.strip('\'"')
	if not re.search(r'[a-zA-Z]', string):
		return True # ignore without any letter
	elif len(string) < 3:
		return True # ignore 'w' etc.
	elif re.match(r'^</?\w+>$', string):
		return True # ignore open / close XML tags 
	elif string.startswith('zim.'):
		return True # module names
	elif string.startswith('BUG'):
		return True # assertion (?)
	elif string.startswith('TODO'):
		return True # assertion (?)
	
	return False

ignore_functions = ('setdefault', 'connect', 'connect_after', 'connect_object', 'get_property', 'emit', 'info', 'debug', 'warn', 'exception', 'get_action') 


class Internationalizer(Gtk.Window):

	def __init__(self):
	#~ def __init__(self, dir):
		GObject.GObject.__init__(self)
		self.set_title('Internationalizer')
		self.set_default_size(500, 500)
		#~ self.dir = dir

		vbox = Gtk.VBox()
		self.add(vbox)

		self.status_label = Gtk.Label()
		vbox.pack_start(self.status_label, False)

		hbox = Gtk.HBox()
		vbox.add(hbox)
		scrollwindow = Gtk.ScrolledWindow()
		hbox.add(scrollwindow)

		self.textview = Gtk.TextView()
		self.textview.set_left_margin(12)
		self.textview.set_right_margin(5)
		scrollwindow.add(self.textview)

		bbox = Gtk.HButtonBox()
		vbox.pack_start(bbox, False)

		savebutton = Gtk.Button(stock='gtk-save')
		savebutton.connect_object('clicked', self.__class__.save_file, self)
		bbox.add(savebutton)

		reloadbutton = Gtk.Button(stock='gtk-refresh')
		reloadbutton.connect_object('clicked', self.__class__.reload_file, self)
		bbox.add(reloadbutton)

		nextbutton = Gtk.Button(stock='gtk-forward')
		nextbutton.connect_object('clicked', self.__class__.next_tag, self)
		bbox.add(nextbutton)

		applybutton = Gtk.Button(stock='gtk-apply')
		applybutton.connect_object('clicked', self.__class__.apply_mark, self)
		bbox.add(applybutton)


	def open_file(self, file):
		if self.textview.get_buffer().get_modified():
			self.save_file()
		self.file = file
		buffer = Gtk.TextBuffer()
		print('Reading %s' % self.file)
		buffer.set_text(open(self.file).read())
		self.textview.set_buffer(buffer)

		buffer.create_tag('translated', background='green')
		buffer.create_tag('untranslated', background='red')
		buffer.create_tag('notsure', background='orange')

		translated, untranslated, notsure = self.tokenize()
		self.status_label.set_text(
			"%i translated, %i untranslated, %i not sure"
			% (len(translated), len(untranslated), len(notsure))
		)

		def get_iter(coord):
			row, col = coord
			row -= 1
			iter = buffer.get_iter_at_line(row)
			iter.forward_chars(col)
			return iter

		for start, end in translated:
			start, end = list(map(get_iter, (start, end)))
			buffer.apply_tag_by_name('translated', start, end)

		for start, end in untranslated:
			start, end = list(map(get_iter, (start, end)))
			buffer.apply_tag_by_name('untranslated', start, end)

		for start, end in notsure:
			start, end = list(map(get_iter, (start, end)))
			buffer.apply_tag_by_name('notsure', start, end)

		buffer.place_cursor(buffer.get_iter_at_offset(0))

	def tokenize(self):
		translated = []
		untranslated = []
		notsure = []
		tokens = tokenize.generate_tokens(open(self.file).readline)

		reset = lambda: {'funcname': None, 'isfunc': False, 'iskey': False}
		state = reset()

		for type, string, start, end, line in tokens:
			if type == token.STRING:
				if state['isfunc'] and state['funcname'] == '_':
					translated.append((start, end))
				elif state['iskey'] or \
				(state['isfunc'] and state['funcname'] in ignore_functions) or \
				match_ignore(string):
					notsure.append((start, end))
				else:
					untranslated.append((start, end))
				state = reset()
			elif type == token.NAME:
				state = reset()
				state['funcname'] = string
			elif type == token.OP and string == '(':
				state['iskey'] = False
				state['isfunc'] = True
			elif type == token.OP and string == '[':
				state['isfunc'] = False
				state['iskey'] = True
			else:
				state = reset()

		return translated, untranslated, notsure

	def save_file(self):
		buffer = self.textview.get_buffer()
		content = buffer.get_text(*buffer.get_bounds())
		print('Writing %s' % self.file)
		open(self.file, 'w').write(content)

	def reload_file(self):
		self.open_file(self.file)

	def next_tag(self):
		'''Select the next untranslated string'''
		buffer = self.textview.get_buffer()
		iter = buffer.get_iter_at_mark(buffer.get_insert())
		tag = buffer.get_tag_table().lookup('untranslated')
		iter.forward_to_tag_toggle(tag)
		if not iter.begins_tag(tag):
			iter.forward_to_tag_toggle(tag)
		bound = iter.copy()
		bound.forward_to_tag_toggle(tag)
		buffer.select_range(iter, bound)
		self.textview.scroll_mark_onscreen(buffer.get_selection_bound())
		self.textview.scroll_mark_onscreen(buffer.get_insert())

	def apply_mark(self):
		'''Wrap current selected string in "_( .. )"'''
		buffer = self.textview.get_buffer()
		bounds = buffer.get_selection_bounds()
		if bounds:
			start, end = bounds
		else:
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			for tag in 'untranslated', 'notsure':
				tag = buffer.get_tag_table().lookup(tag)
				if iter.has_tag(tag):
					iter.backward_to_tag_toggle(tag)
					bound = iter.copy()
					bound.forward_to_tag_toggle(tag)
					start, end = iter, bound
					break
			else:
				return

		buffer.remove_all_tags(start, end)
		buffer.apply_tag_by_name('translated', start, end)
		start, end = start.get_offset(), end.get_offset()
		if start > end:
			start, end = end, start
		buffer.insert(buffer.get_iter_at_offset(end), ')')
		buffer.insert(buffer.get_iter_at_offset(start), '_(')
		self.next_tag()

if __name__ == '__main__':
	import sys
	app = Internationalizer()
	app.open_file(sys.argv[1])
	app.show_all()
	app.connect('destroy', lambda o: Gtk.main_quit())
	Gtk.main()


# Copyright 2010 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains code for defining and managing custom
commands.
'''




from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import GdkPixbuf


import logging

from functools import partial


from zim.fs import File, TmpFile, cleanup_filename
from zim.parsing import split_quoted_strings
from zim.config import ConfigManager, XDG_CONFIG_HOME, INIConfigFile
from zim.signals import SignalEmitter, SIGNAL_NORMAL, SignalHandler

from zim.gui.applications import Application, DesktopEntryDict, \
 	_create_application, String, Boolean
from zim.gui.widgets import Dialog, IconButton, IconChooserButton

import zim.errors

logger = logging.getLogger('zim.gui')


class CustomToolManager(SignalEmitter):
	'''Manager for dealing with the desktop files which are used to
	store custom tools.

	Custom tools are external commands that are intended to show in the
	"Tools" menu in zim (and optionally in the tool bar). They are
	defined as desktop entry files in a special folder (typically
	"~/.local/share/zim/customtools") and use several non standard keys.
	See L{CustomTool} for details.

	This object is iterable and maintains a specific order for tools
	to be shown in in the user interface.
	'''

	__signals__ = {
		'changed': (SIGNAL_NORMAL, None, ())
	}

	def __init__(self):
		self._names = []
		self._tools = {}
		self._listfile = ConfigManager.get_config_file('customtools/customtools.list')
		self._read_list()
		self._listfile.connect('changed', self._on_list_changed)

	@SignalHandler
	def _on_list_changed(self, *a):
		self._read_list()
		self.emit('changed')

	def _on_tool_changed(self, tool, *a):
		if not tool.modified: # XXX: modified means this is the instance that is writing
			tool.read()
		self.emit('changed')

	def _read_list(self):
		self._names = []
		seen = set()
		for line in self._listfile.readlines():
			name = line.strip()
			if not name in seen:
				seen.add(name)
				self._names.append(name)

	def _write_list(self):
		with self._on_list_changed.blocked():
			self._listfile.writelines([name + '\n' for name in self._names])
		self.emit('changed')

	def __iter__(self):
		for name in self._names:
			tool = self.get_tool(name)
			if tool and tool.isvalid():
				yield tool

	def get_tool(self, name):
		'''Get a L{CustomTool} by name.
		@param name: the tool name
		@returns: a L{CustomTool} object or C{None}
		'''
		if not '-usercreated' in name:
			name = cleanup_filename(name.lower()) + '-usercreated'

		if not name in self._tools:
			file = ConfigManager.get_config_file('customtools/%s.desktop' % name)
			if file.exists():
				tool = CustomTool(file)
				self._tools[name] = tool
				file.connect('changed', partial(self._on_tool_changed, tool))
			else:
				return None

		return self._tools[name]

	def create(self, Name, **properties):
		'''Create a new custom tool

		@param Name: the name to show in the Tools menu
		@param properties: properties for the custom tool, e.g.:
		  - Comment
		  - Icon
		  - X-Zim-ExecTool
		  - X-Zim-ReadOnly
		  - X-Zim-ShowInToolBar

		@returns: a new L{CustomTool} object.
		'''
		properties['Type'] = 'X-Zim-CustomTool'
		dir = XDG_CONFIG_HOME.subdir('zim/customtools')
		tool = _create_application(dir, Name, '', klass=CustomTool, NoDisplay=False, **properties)

		# XXX - hack to ensure we link to configmanager
		file = ConfigManager.get_config_file('customtools/' + tool.file.basename)
		tool.file = file
		file.connect('changed', partial(self._on_tool_changed, tool))

		self._tools[tool.key] = tool
		self._names.append(tool.key)
		self._write_list()

		return tool

	def delete(self, tool):
		'''Remove a custom tool from the list and delete the definition
		file.
		@param tool: a custom tool name or L{CustomTool} object
		'''
		if not isinstance(tool, CustomTool):
			tool = self.get_tool(tool)
		tool.file.remove()
		self._tools.pop(tool.key)
		self._names.remove(tool.key)
		self._write_list()

	def index(self, tool):
		'''Get the position of a specific tool in the list.
		@param tool: a custom tool name or L{CustomTool} object
		@returns: an integer for the position
		'''
		if isinstance(tool, CustomTool):
			tool = tool.key
		return self._names.index(tool)

	def reorder(self, tool, i):
		'''Change the position of a tool in the list.
		@param tool: a custom tool name or L{CustomTool} object
		@param i: the new position as integer
		'''
		if not 0 <= i < len(self._names):
			return

		if isinstance(tool, CustomTool):
			tool = tool.key

		j = self._names.index(tool)
		self._names.pop(j)
		self._names.insert(i, tool)
		# Insert before i. If i was before old position indeed before
		# old item at that position. However if i was after old position
		# if shifted due to the pop(), now it inserts after the old item.
		# This is intended behavior to make all moves possible.
		self._write_list()



from zim.config import Choice

class CustomToolDict(DesktopEntryDict):
	'''This is a specialized desktop entry type that is used for
	custom tools for the "Tools" menu in zim. It uses a non-standard
	Exec spec with zim specific escapes for "X-Zim-ExecTool".

	The following fields are expanded:
		- C{%f} for source file as tmp file current page
		- C{%d} for attachment directory
		- C{%s} for real source file (if any)
		- C{%n} for notebook location (file or directory)
		- C{%D} for document root
		- C{%t} for selected text or word under cursor
		- C{%T} for the selected text including wiki formatting

	Other additional keys are:
		- C{X-Zim-ReadOnly} - boolean
		- C{X-Zim-ShowInToolBar} - boolean
		- C{X-Zim-ShowInContextMenu} - 'None', 'Text' or 'Page'

	These tools should always be executed with 3 arguments: notebook,
	page & pageview.
	'''

	_definitions = DesktopEntryDict._definitions + (
			('X-Zim-ExecTool', String(None)),
			('X-Zim-ReadOnly', Boolean(True)),
			('X-Zim-ShowInToolBar', Boolean(False)),
			('X-Zim-ShowInContextMenu', Choice(None, ('Text', 'Page'))),
			('X-Zim-ReplaceSelection', Boolean(False)),
	)

	def isvalid(self):
		'''Check if all required fields are set.
		@returns: C{True} if all required fields are set
		'''
		entry = self['Desktop Entry']
		if entry.get('Type') == 'X-Zim-CustomTool' \
		and entry.get('Version') == 1.0 \
		and entry.get('Name') \
		and entry.get('X-Zim-ExecTool') \
		and not entry.get('X-Zim-ReadOnly') is None \
		and not entry.get('X-Zim-ShowInToolBar') is None \
		and 'X-Zim-ShowInContextMenu' in entry:
			return True
		else:
			logger.error('Invalid custom tool entry: %s %s', self.key, entry)
			return False

	def get_pixbuf(self, size):
		pixbuf = DesktopEntryDict.get_pixbuf(self, size)
		if pixbuf is None:
			pixbuf = Gtk.Label().render_icon(Gtk.STOCK_EXECUTE, size)
			# FIXME hack to use arbitrary widget to render icon
		return pixbuf

	@property
	def icon(self):
		return self['Desktop Entry'].get('Icon') or Gtk.STOCK_EXECUTE
			# get('Icon', Gtk.STOCK_EXECUTE) still returns empty string if key exists but no value

	@property
	def execcmd(self):
		return self['Desktop Entry']['X-Zim-ExecTool']

	@property
	def isreadonly(self):
		return self['Desktop Entry']['X-Zim-ReadOnly']

	@property
	def showintoolbar(self):
		return self['Desktop Entry']['X-Zim-ShowInToolBar']

	@property
	def showincontextmenu(self):
		return self['Desktop Entry']['X-Zim-ShowInContextMenu']

	@property
	def replaceselection(self):
		return self['Desktop Entry']['X-Zim-ReplaceSelection']

	def parse_exec(self, args=None):
		if not (isinstance(args, tuple) and len(args) == 3):
			raise AssertionError('Custom commands needs 3 arguments')
			# assert statement could be optimized away
		notebook, page, pageview = args

		cmd = split_quoted_strings(self['Desktop Entry']['X-Zim-ExecTool'])
		if '%f' in cmd:
			self._tmpfile = TmpFile('tmp-page-source.txt')
			self._tmpfile.writelines(page.dump('wiki'))
			cmd[cmd.index('%f')] = self._tmpfile.path

		if '%d' in cmd:
			dir = notebook.get_attachments_dir(page)
			if dir:
				cmd[cmd.index('%d')] = dir.path
			else:
				cmd[cmd.index('%d')] = ''

		if '%s' in cmd:
			if hasattr(page, 'source') and isinstance(page.source, File):
				cmd[cmd.index('%s')] = page.source.path
			else:
				cmd[cmd.index('%s')] = ''

		if '%p' in cmd:
			cmd[cmd.index('%p')] = page.name

		if '%n' in cmd:
			cmd[cmd.index('%n')] = File(notebook.uri).path

		if '%D' in cmd:
			dir = notebook.document_root
			if dir:
				cmd[cmd.index('%D')] = dir.path
			else:
				cmd[cmd.index('%D')] = ''

		if '%t' in cmd:
			text = pageview.get_selection() or pageview.get_word()
			cmd[cmd.index('%t')] = text or ''
			# FIXME - need to substitute this in arguments + url encoding

		if '%T' in cmd:
			text = pageview.get_selection(format='wiki') or pageview.get_word(format='wiki')
			cmd[cmd.index('%T')] = text or ''
			# FIXME - need to substitute this in arguments + url encoding

		return tuple(cmd)

	_cmd = parse_exec # To hook into Application.spawn and Application.run

	def run(self, args, cwd=None):
		self._tmpfile = None
		Application.run(self, args, cwd=cwd)
		if self._tmpfile:
			notebook, page, pageview = args
			page.parse('wiki', self._tmpfile.readlines())
			notebook.store_page(page)
			self._tmpfile = None

	def update(self, E=(), **F):
		self['Desktop Entry'].update(E, **F)

		# Set sane default for X-Zim-ShowInContextMenus
		if not (E and 'X-Zim-ShowInContextMenu' in E) \
		and not 'X-Zim-ShowInContextMenu' in F:
			cmd = split_quoted_strings(self['Desktop Entry']['X-Zim-ExecTool'])
			if any(c in cmd for c in ['%f', '%d', '%s']):
				context = 'Page'
			elif '%t' in cmd:
				context = 'Text'
			else:
				context = None
			self['Desktop Entry']['X-Zim-ShowInContextMenu'] = context


class CustomTool(CustomToolDict, INIConfigFile):
	'''Class representing a file defining a custom tool, see
	L{CustomToolDict} for the API documentation.
	'''

	def __init__(self, file):
		CustomToolDict.__init__(self)
		INIConfigFile.__init__(self, file)

	@property
	def key(self):
		return self.file.basename[:-8] # len('.desktop') is 8


class StubPageView(object):

	def __init__(self, notebook, page):
		self.notebook = notebook
		self.page = page

	def save_changes(self):
		pass

	def get_selection(self, format=None):
		return None

	def get_word(self, format=None):
		return None

	def replace_selection(self, string):
		raise NotImplementedError


class CustomToolManagerUI(object):

	def __init__(self, uimanager, pageview):
		'''Constructor
		@param uimanager: a C{Gtk.UIManager}
		@param pageview: either a L{PageView} or a L{StubPageView}
		'''
		# TODO check via abc base class ?
		assert hasattr(pageview, 'notebook')
		assert hasattr(pageview, 'page')
		assert hasattr(pageview, 'get_selection')
		assert hasattr(pageview, 'get_word')
		assert hasattr(pageview, 'save_changes')
		assert hasattr(pageview, 'replace_selection')

		self.uimanager = uimanager
		self.pageview = pageview

		self._manager = CustomToolManager()
		self._iconfactory = Gtk.IconFactory()
		self._iconfactory.add_default()
		self._ui_id = None
		self._actiongroup = None

		self.add_customtools()
		self._manager.connect('changed', self.on_changed)

	def on_changed(self, o):
		self.uimanager.remove_ui(self._ui_id)
		self.uimanager.remove_action_group(self._actiongroup)
		self._ui_id = None
		self._actiongroup = None
		self.add_customtools()

	def add_customtools(self):
		assert self._ui_id is None
		assert self._actiongroup is None

		self._actiongroup = self.get_actiongroup()
		ui_xml = self.get_ui_xml()

		self.uimanager.insert_action_group(self._actiongroup, 0)
		self._ui_id = self.uimanager.add_ui_from_string(ui_xml)

	def get_actiongroup(self):
		actions = []
		for tool in self._manager:
			icon = tool.icon
			if '/' in icon or '\\' in icon:
				# Assume icon is a file path - need to add it in order to make it loadable
				icon = 'zim-custom-tool' + tool.key
				try:
					pixbuf = tool.get_pixbuf(Gtk.IconSize.LARGE_TOOLBAR)
					self._iconfactory.add(icon, Gtk.IconSet(pixbuf=pixbuf))
				except Exception:
					logger.exception('Got exception while loading application icons')
					icon = None

			actions.append(
				(tool.key, icon, tool.name, '', tool.comment, self._action_handler)
			)

		group = Gtk.ActionGroup('custom_tools')
		group.add_actions(actions)
		return group

	def get_ui_xml(self):
		tools = self._manager
		menulines = ["<menuitem action='%s'/>\n" % t.key for t in tools]
		toollines = ["<toolitem action='%s'/>\n" % t.key for t in tools if t.showintoolbar]
		textlines = ["<menuitem action='%s'/>\n" % t.key for t in tools if t.showincontextmenu == 'Text']
		pagelines = ["<menuitem action='%s'/>\n" % t.key for t in tools if t.showincontextmenu == 'Page']
		return """\
		<ui>
			<menubar name='menubar'>
				<menu action='tools_menu'>
					<placeholder name='custom_tools'>
					 %s
					</placeholder>
				</menu>
			</menubar>
			<toolbar name='toolbar'>
				<placeholder name='tools'>
				%s
				</placeholder>
			</toolbar>
			<popup name='text_popup'>
				<placeholder name='tools'>
				%s
				</placeholder>
			</popup>
			<popup name='page_popup'>
				<placeholder name='tools'>
				%s
				</placeholder>
			</popup>
		</ui>
		""" % (
			''.join(menulines),
			''.join(toollines),
			''.join(textlines),
			''.join(pagelines)
		)

	def _action_handler(self, action):
		tool = self._manager.get_tool(action.get_name())
		logger.info('Execute custom tool %s', tool.name)
		try:
			self._exec_custom_tool(tool)
		except:
			zim.errors.exception_handler(
				'Exception during action: %s' % tool.name)

	def _exec_custom_tool(self, tool):
		# FIXME: should this not be part of tool.run() ?
		pageview = self.pageview
		notebook, page = pageview.notebook, pageview.page
		args = (notebook, page, pageview)
		cwd = page.source_file.parent()

		pageview.save_changes()
		if tool.replaceselection:
			output = tool.pipe(args, cwd=cwd)
			logger.debug('Replace selection with: %s', output)
			pageview.replace_selection(output, autoselect='word')
		elif tool.isreadonly:
			tool.spawn(args, cwd=cwd)
		else:
			tool.run(args, cwd=cwd)
			pageview.page.check_source_changed()
			notebook.index.start_background_check(notebook)
			# TODO instead of using run, use spawn and show dialog
			# with cancel button. Dialog blocks ui.


class CustomToolManagerDialog(Dialog):

	def __init__(self, parent):
		Dialog.__init__(self, parent, _('Custom Tools'), buttons=Gtk.ButtonsType.CLOSE) # T: Dialog title
		self.set_help(':Help:Custom Tools')
		self.manager = CustomToolManager()

		self.add_help_text(_(
			'You can configure custom tools that will appear\n'
			'in the tool menu and in the tool bar or context menus.'
		)) # T: help text in "Custom Tools" dialog

		hbox = Gtk.HBox(spacing=5)
		self.vbox.pack_start(hbox, True, True, 0)

		self.listview = CustomToolList(self.manager)
		hbox.pack_start(self.listview, True, True, 0)

		vbox = Gtk.VBox(spacing=5)
		hbox.pack_start(vbox, False, True, 0)

		for stock, handler, data in (
			(Gtk.STOCK_ADD, self.__class__.on_add, None),
			(Gtk.STOCK_EDIT, self.__class__.on_edit, None),
			(Gtk.STOCK_DELETE, self.__class__.on_delete, None),
			(Gtk.STOCK_GO_UP, self.__class__.on_move, -1),
			(Gtk.STOCK_GO_DOWN, self.__class__.on_move, 1),
		):
			button = IconButton(stock) # TODO tooltips for icon button
			if data:
				button.connect_object('clicked', handler, self, data)
			else:
				button.connect_object('clicked', handler, self)
			vbox.pack_start(button, False, True, 0)

	def on_add(self):
		properties = EditCustomToolDialog(self).run()
		if properties:
			self.manager.create(**properties)
		self.listview.refresh()

	def on_edit(self):
		name = self.listview.get_selected()
		if name:
			tool = self.manager.get_tool(name)
			properties = EditCustomToolDialog(self, tool=tool).run()
			if properties:
				tool.update(**properties)
				tool.write()
		self.listview.refresh()

	def on_delete(self):
		name = self.listview.get_selected()
		if name:
			self.manager.delete(name)
			self.listview.refresh()

	def on_move(self, step):
		name = self.listview.get_selected()
		if name:
			i = self.manager.index(name)
			self.manager.reorder(name, i + step)
			self.listview.refresh()
			self.listview.select(i + step)


class CustomToolList(Gtk.TreeView):

	PIXBUF_COL = 0
	TEXT_COL = 1
	NAME_COL = 2

	def __init__(self, manager):
		GObject.GObject.__init__(self)
		self.manager = manager

		model = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str)
				# PIXBUF_COL, TEXT_COL, NAME_COL
		self.set_model(model)
		self.set_headers_visible(False)

		self.get_selection().set_mode(Gtk.SelectionMode.BROWSE)

		cr = Gtk.CellRendererPixbuf()
		column = Gtk.TreeViewColumn('_pixbuf_', cr, pixbuf=self.PIXBUF_COL)
		self.append_column(column)

		cr = Gtk.CellRendererText()
		column = Gtk.TreeViewColumn('_text_', cr, markup=self.TEXT_COL)
		self.append_column(column)

		self.refresh()

	def get_selected(self):
		model, iter = self.get_selection().get_selected()
		if model and iter:
			return model[iter][self.NAME_COL]
		else:
			return None

	def select(self, i):
		path = (i, )
		self.get_selection().select_path(path)

	def select_by_name(self, name):
		for i, r in enumerate(self.get_model()):
			if r[self.NAME_COL] == name:
				return self.select(i)
		else:
			raise ValueError

	def refresh(self):
		from zim.gui.widgets import encode_markup_text
		model = self.get_model()
		model.clear()
		for tool in self.manager:
			pixbuf = tool.get_pixbuf(Gtk.IconSize.MENU)
			text = '<b>%s</b>\n%s' % (encode_markup_text(tool.name), encode_markup_text(tool.comment))
			model.append((pixbuf, text, tool.key))


class EditCustomToolDialog(Dialog):

	def __init__(self, parent, tool=None):
		Dialog.__init__(self, parent, _('Edit Custom Tool')) # T: Dialog title
		self.set_help(':Help:Custom Tools')
		self.vbox.set_spacing(12)

		if tool:
			name = tool.name
			comment = tool.comment
			execcmd = tool.execcmd
			readonly = tool.isreadonly
			toolbar = tool.showintoolbar
			replaceselection = tool.replaceselection
		else:
			name = ''
			comment = ''
			execcmd = ''
			readonly = False
			toolbar = False
			replaceselection = False

		self.add_form((
			('Name', 'string', _('Name')), # T: Input in "Edit Custom Tool" dialog
			('Comment', 'string', _('Description')), # T: Input in "Edit Custom Tool" dialog
			('X-Zim-ExecTool', 'string', _('Command')), # T: Input in "Edit Custom Tool" dialog
		), {
			'Name': name,
			'Comment': comment,
			'X-Zim-ExecTool': execcmd,
		}, trigger_response=False)

		# FIXME need ui builder to take care of this as well
		self.iconbutton = IconChooserButton(stock=Gtk.STOCK_EXECUTE)
		if tool and tool.icon and tool.icon != Gtk.STOCK_EXECUTE:
			try:
				self.iconbutton.set_file(File(tool.icon))
			except Exception as error:
				logger.exception('Could not load: %s', tool.icon)
		label = Gtk.Label(label=_('Icon') + ':') # T: Input in "Edit Custom Tool" dialog
		label.set_alignment(0.0, 0.5)
		hbox = Gtk.HBox()
		i = self.form.get_property('n-rows')
		self.form.attach(label, 0, 1, i, i + 1, xoptions=0)
		self.form.attach(hbox, 1, 2, i, i + 1)
		hbox.pack_start(self.iconbutton, False, True, 0)

		self.form.add_inputs((
			('X-Zim-ReadOnly', 'bool', _('Command does not modify data')), # T: Input in "Edit Custom Tool" dialog
			('X-Zim-ReplaceSelection', 'bool', _('Output should replace current selection')), # T: Input in "Edit Custom Tool" dialog
			('X-Zim-ShowInToolBar', 'bool', _('Show in the toolbar')), # T: Input in "Edit Custom Tool" dialog
		))
		self.form.update({
			'X-Zim-ReadOnly': readonly,
			'X-Zim-ReplaceSelection': replaceselection,
			'X-Zim-ShowInToolBar': toolbar,
		})

		self.add_help_text(_('''\
The following parameters will be substituted
in the command when it is executed:
<tt>
<b>%f</b> the page source as a temporary file
<b>%d</b> the attachment directory of the current page
<b>%s</b> the real page source file (if any)
<b>%p</b> the page name
<b>%n</b> the notebook location (file or folder)
<b>%D</b> the document root (if any)
<b>%t</b> the selected text or word under cursor
<b>%T</b> the selected text including wiki formatting
</tt>
''') ) # T: Short help text in "Edit Custom Tool" dialog. The "%" is literal - please include the html formatting

	def do_response_ok(self):
		fields = self.form.copy()
		fields['Icon'] = self.iconbutton.get_file() or None
		self.result = fields
		return True

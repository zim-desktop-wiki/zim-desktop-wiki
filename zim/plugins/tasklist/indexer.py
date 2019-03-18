
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import logging
import re
import sqlite3

import zim.datetimetz as datetime

from zim.notebook import Path
from zim.notebook.index.base import IndexerBase, IndexView
from zim.notebook.index.pages import PagesViewInternal
from zim.formats import get_format, \
	UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX, BULLET, TAG, \
	HEADING, PARAGRAPH, BLOCK, NUMBEREDLIST, BULLETLIST, LISTITEM, STRIKE, \
	Visitor, VisitorSkip
from zim.tokenparser import skip_to_end_token, TEXT, END

from zim.plugins.journal import daterange_from_path
	# TODO instead of just importing this function we should define
	#      an interface or hook to call the journal plugin object

logger = logging.getLogger('zim.plugins.tasklist')


from zim.parsing import parse_date as old_parse_date
from .dates import date_re as _raw_parse_date_re
from .dates import parse_date


_tag_re = re.compile(r'(?<!\S)@(\w+)\b', re.U)
_date_re = re.compile('[<>] ?' + _raw_parse_date_re.pattern + '|\[d:.+\]')
	# "<" and ">" prefixes for dates, "[d: ...]" for backward compatibility

_MAX_DUE_DATE = '9999' # Constant for empty due date - value chosen for sorting properties
_NO_TAGS = '__no_tags__' # Constant that serves as the "no tags" tag - _must_ be lower case




def _parse_task_labels(string):
	if string is None:
		return []
	else:
		return [
			s.strip()
				for s in string.split(',')
					if s and not s.isspace()
		]


def _task_labels_re(labels):
	return re.compile(
		r'^(' + '|'.join(re.escape(l.strip(':')) for l in labels) + r')(?!\w)'
	)

def _parse_page_list(input):
	paths = []
	if not input or not input.strip():
		return paths

	for name in input.split(','):
		try:
			paths.append(Path(Path.makeValidPageName(name.strip())))
		except ValueError:
			logger.warn('Could not parse page name: "%s"', name)
	return paths


class TasksIndexer(IndexerBase):
	'''Indexer that gets added to the L{Index} to keep track of tasks
	in the database
	'''

	PLUGIN_NAME = "tasklist"
	PLUGIN_DB_FORMAT = "0.8"

	INIT_SCRIPT = '''
		CREATE TABLE IF NOT EXISTS tasklist (
			id INTEGER PRIMARY KEY,
			source INTEGER,
			parent INTEGER,
			haschildren BOOLEAN,
			hasopenchildren BOOLEAN,
			open BOOLEAN,
			prio INTEGER,
			start TEXT,
			due TEXT,
			tags TEXT,
			description TEXT
		);
		INSERT OR REPLACE INTO zim_index VALUES (%r, %r);
	''' % (PLUGIN_NAME, PLUGIN_DB_FORMAT)

	TEARDOWN_SCRIPT = '''
		DROP TABLE IF EXISTS "tasklist";
		DELETE FROM zim_index WHERE key = %r;
	''' % PLUGIN_NAME

	__signals__ = {
		'tasklist-changed': (None, None, ()),
	}

	@classmethod
	def new_from_index(cls, index, properties):
		db = index._db
		pagesindexer = index.update_iter.pages
		return cls(db, pagesindexer, properties)

	def __init__(self, db, pagesindexer, properties):
		IndexerBase.__init__(self, db)

		self.parser = TaskParser(
			task_label_re=_task_labels_re(
				_parse_task_labels(
					properties['labels'])),
			all_checkboxes=properties['all_checkboxes'],
		)

		self.integrate_with_journal = properties['integrate_with_journal']
		self.included_subtrees = _parse_page_list(properties['included_subtrees'])
		self.excluded_subtrees = _parse_page_list(properties['excluded_subtrees'])
		self.db.executescript(self.INIT_SCRIPT)

		self.connectto_all(pagesindexer, (
			'page-changed', 'page-row-deleted'
		))

	def on_page_changed(self, o, row, doc):
		changes = False
		count, = self.db.execute(
			'SELECT count(*) FROM tasklist WHERE source=?',
			(row['id'],)
		).fetchone()
		if count > 0:
			self.db.execute(
				'DELETE FROM tasklist WHERE source=?',
				(row['id'],)
			)
			changes = True

		mypath = Path(row['name'])
		if self.included_subtrees:
			if not any(mypath.match_namespace(n) for n in self.included_subtrees):
				if changes:
					self.emit('tasklist-changed')
				return
		if self.excluded_subtrees:
			if any(mypath.match_namespace(n) for n in self.excluded_subtrees):
				if changes:
					self.emit('tasklist-changed')
				return

		opts = {}
		if self.integrate_with_journal:
			date = daterange_from_path(Path(row['name']))
			if date and self.integrate_with_journal == 'start':
				opts['default_start_date'] = date[1]
			elif date and self.integrate_with_journal == 'due':
				opts['default_due_date'] = date[2]

		tasks = self.parser.parse(doc.iter_tokens(), **opts)
		c = self.db.cursor()
		count = c.rowcount
		self._insert_tasks(c, row['id'], 0, tasks)
		if changes or c.rowcount > count:
			self.emit('tasklist-changed')

	def _insert_tasks(self, db, pageid, parentid, tasks):
		# Helper function to insert tasks in table
		for task, children in tasks:
			task[4] = ','.join(sorted(task[4])) # make tag list a string
			db.execute(
				'INSERT INTO tasklist(source, parent, haschildren, hasopenchildren, open, prio, start, due, tags, description)'
				'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
				(pageid, parentid, bool(children), any(c[0][0] for c in children)) + tuple(task)
			)
			if children:
				self._insert_tasks(db, pageid, db.lastrowid, children) # recurs

	def on_page_row_deleted(self, o, row):
		count, = self.db.execute(
			'SELECT count(*) FROM tasklist WHERE source=?',
			(row['id'],)
		).fetchone()
		if count > 0:
			self.db.execute(
				'DELETE FROM tasklist WHERE source=?',
				(row['id'],)
			)
			self.emit('tasklist-changed')


class TasksView(IndexView):
	'''Database "view" that shows tasks that are indexed'''

	def __init__(self, db):
		IndexView.__init__(self, db)
		self._pages = PagesViewInternal(db)

		# Test the db really has a tasklist
		try:
			db.execute('SELECT * FROM tasklist LIMIT 1')
		except sqlite3.OperationalError:
			raise ValueError('No tasklist in index')

	def list_open_tasks(self, parent=None):
		'''List tasks
		@param parent: the parent task (as returned by this method) or C{None} to list
		all top level tasks
		@returns: a list of tasks at this level as sqlite Row objects
		'''
		if parent:
			parentid = parent['id']
		else:
			parentid = 0

		# Sort:
		#  started tasks by prio, due date, page + id to keep order in page
		#  not-started tasks by start date, ...
		today = str(datetime.date.today())
		for row in self.db.execute('''
			SELECT tasklist.* FROM tasklist
			LEFT JOIN pages ON tasklist.source = pages.id
			WHERE tasklist.open=1 and tasklist.parent=? and tasklist.start<=?
			ORDER BY tasklist.prio DESC, tasklist.due ASC, pages.name ASC, tasklist.id ASC
			''', (parentid, today)
		):
			yield row
		for row in self.db.execute('''
			SELECT tasklist.* FROM tasklist
			LEFT JOIN pages ON tasklist.source = pages.id
			WHERE tasklist.open=1 and tasklist.parent=? and tasklist.start>?
			ORDER BY tasklist.start ASC, tasklist.prio DESC, tasklist.due ASC, pages.name ASC, tasklist.id ASC
			''', (parentid, today)
		):
			yield row

	def list_open_tasks_flatlist(self):
		'''List tasks
		@returns: a list of tasks as sqlite Row objects
		'''
		# Sort:
		#  started tasks by prio, due date, page + id to keep order in page
		#  not-started tasks by start date, ...
		today = str(datetime.date.today())
		for row in self.db.execute('''
			SELECT tasklist.* FROM tasklist
			LEFT JOIN pages ON tasklist.source = pages.id
			WHERE tasklist.open=1 and tasklist.start<=? and hasopenchildren=0
			ORDER BY tasklist.prio DESC, tasklist.due ASC, pages.name ASC, tasklist.id ASC
			''', (today,)
		):
			yield row
		for row in self.db.execute('''
			SELECT tasklist.* FROM tasklist
			LEFT JOIN pages ON tasklist.source = pages.id
			WHERE tasklist.open=1 and tasklist.start>? and hasopenchildren=0
			ORDER BY tasklist.start ASC, tasklist.prio DESC, tasklist.due ASC, pages.name ASC, tasklist.id ASC
			''', (today,)
		):
			yield row

	def get_task(self, taskid):
		row = self.db.execute(
			'SELECT * FROM tasklist WHERE id=?',
			(taskid,)
		).fetchone()
		return row

	def get_path(self, task):
		'''Get the L{Path} for the source of a task
		@param task: the task (as returned by L{list_tasks()}
		@returns: an L{IndexPath} object
		'''
		return self._pages.get_pagename(task['source'])


class TaskParser(object):

	# This parser uses the "top level lists" representation to separate
	# lists from paragraphs.
	#
	# For paragraph:
	#	- Lines that start with label
	#
	# For list:
	#	- Decent to find checkbox items (all-checkboxes option)
	#	- All bullet types with label
	#	- Check parent for inheritance etc.
	#
	# Special case is the "heading line" above a list which consists
	# of label and optional tags.
	# This shows up as a task without description in a one-line paragraph
	# immediatly in front of a list.

	def __init__(self,
			task_label_re=_task_labels_re(['TODO', 'FIXME']),
			all_checkboxes=True,
	):
		self.task_label_re = task_label_re
		self.all_checkboxes = all_checkboxes

	def parse(self, tokens, default_start_date=0, default_due_date=_MAX_DUE_DATE):

		defaults = [True, 0, default_start_date, default_due_date]
					# [isopen, prio, start, due]

		def _is_list_heading(task):
			isopen, prio, start, due, tags, text = task[0]
			words = text.strip().split()
			if self.task_label_re.match(words[0]) \
			and all(w.startswith('@') or w == ':' for w in words[1:]):
				return True

		tasks = []
		token_iter = iter(tokens)

		check_list_heading = False
		for t in token_iter:
			if t[0] == HEADING:
				task = self._parse_heading(token_iter)
				if task:
					tasks.append(task)
			elif t[0] == PARAGRAPH:
				paratasks = self._parse_paragraph(token_iter, defaults)
				check_list_heading = (len(paratasks) == 1) # Para should be single line -- ### TODO that is not strictly tested here!
				tasks.extend(paratasks)
			elif t[0] in (BULLETLIST, NUMBEREDLIST):
				tags = []
				check_labels = not self.all_checkboxes
				if check_list_heading:
					if _is_list_heading(tasks[-1]):
						heading = tasks.pop()
						isopen, prio, start, due, tags, text = heading[0]
						check_labels = check_labels and not self.task_label_re.match(''.join(text))

				listtasks = self._parse_list(token_iter, tags=tags, parent=defaults, check_labels=check_labels)
				tasks.extend(listtasks)
				check_list_heading = False
			else:
				check_list_heading = False
				continue # Skip other toplevel content

		return tasks

	def _parse_heading(self, token_iter):
		head = []
		for t in token_iter:
			if t == (END, HEADING):
				break
			else:
				head.append(t)

		if self._starts_with_label(head):
			fields = self._task_from_tokens(head)
			return (fields, [])
		else:
			return None

	def _starts_with_label(self, tokens):
		text = []
		for t in tokens:
			if t[0] == STRIKE:
				break
			elif t[0] == TEXT:
				text.append(t[1])
				if ' ' in text:
					break

		return self.task_label_re.match(''.join(text))

	def _parse_paragraph(self, token_iter, defaults):

		def _next_line():
			# Return line as list of tokens
			line = []
			for t in token_iter:
				if t == (END, PARAGRAPH):
					assert not line or len(line) == 1 and line[0] == (END, BLOCK)
					return None
				else:
					line.append(t)
					if t[0] == TEXT and t[1].endswith('\n'):
						return line

		# Look for lines that define tasks
		tasks = []

		while True:
			line = _next_line()
			if not line:
				break # end of PARAGRAPH
			elif self._starts_with_label(line):
				fields = self._task_from_tokens(line, parent=defaults)
				tasks.append((fields, []))

		return tasks

	def _parse_list(self, token_iter, parent=None, tags=[], check_labels=False):
		tasks = []

		for t in token_iter:
			if t[0] == LISTITEM:
				bullet = t[1].get('bullet')
				line = []
				for t in token_iter:
					if t[0] in (BULLETLIST, NUMBEREDLIST) \
					or t == (END, LISTITEM):
						next_token = t
						break
					else:
						line.append(t)

				if (not check_labels and bullet in (CHECKED_BOX, UNCHECKED_BOX, XCHECKED_BOX))\
				or self._starts_with_label(line):
					fields = self._task_from_tokens(
						line,
						isopen=(bullet in (BULLET, UNCHECKED_BOX)),
						parent=parent,
						tags=tags
					)
					tasks.append((fields, []))
					parent_item = tasks[-1]
				else:
					parent_item = None
						# Since this line is not a task, sub-items will be added to top level list

				if next_token[0] in (BULLETLIST, NUMBEREDLIST):
					# Sub-list
					if parent_item:
						mytasks = self._parse_list(token_iter, parent=parent_item[0], tags=parent_item[0][4], check_labels=check_labels) # recurs
						parent_item[-1].extend(mytasks)
						if any(t[0][0] for t in mytasks):
							parent_item[0][0] = True # Force parent open if any child is
					else:
						mytasks = self._parse_list(token_iter, parent=parent, check_labels=check_labels) # recurs
						tasks.extend(mytasks)

					next_token = next(token_iter)
					if not next_token == (END, LISTITEM):
						logger.warn('Unexpected token in list: %r', next_token)

			elif t[0] == END and t[1] in (BULLETLIST, NUMBEREDLIST):
				break
			else:
				logger.warn('Unexpected token in list: %r', t)

		return tasks

	def _task_from_tokens(self, tokens, isopen=True, tags=[], parent=None):
		# Collect text and returns task

		text = []
		tags = set(tags) # copy

		token_iter = iter(tokens)
		for t in token_iter:
			if t[0] == TEXT:
				text.append(t[1])
			elif t[0] == TAG:
				tags.add(t[1]['name'])
			elif t[0] == STRIKE:
				skip_to_end_token(token_iter, STRIKE)
			else:
				pass # ignore all other markup

		return self._task_from_text(''.join(text), isopen, tags, parent)

	def _task_from_text(self, text, isopen=True, tags=None, parent=None):
		# Return task record for single line of text

		prio = text.count('!')
		if prio == 0 and parent:
			prio = parent[1] # inherit prio

		start = parent[2] if parent else 0 # inherit start date
		due = parent[3] if parent else _MAX_DUE_DATE # inherit due date
		for string in _date_re.findall(text):
			try:
				if string.startswith('[d:'): # backward compat
					date = old_parse_date(string[3:-1].strip())
					if date:
						(year, month, day) = date
						due = datetime.date(year, month, day).isoformat()
				elif string.startswith('>'):
					start = parse_date(string[1:]).first_day.isoformat()
				elif string.startswith('<'):
					due = parse_date(string[1:]).last_day.isoformat()
				else:
					logger.warn('False postive matching date: %s', string)
			except ValueError:
				logger.warn('Invalid date format in task: %s', string)

		return [isopen, prio, start, due, tags, str(text.strip())]
			# 0:open, 1:prio, 2:start, 3:due, 4:tags, 5:desc

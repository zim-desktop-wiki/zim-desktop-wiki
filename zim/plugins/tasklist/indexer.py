
# Copyright 2009-2020 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import logging
import re
import sqlite3

import zim.datetimetz as datetime

from zim.notebook import Path
from zim.notebook.index.base import IndexerBase, IndexView
from zim.notebook.index.pages import PagesViewInternal
from zim.formats import get_format, \
	UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX, MIGRATED_BOX, TRANSMIGRATED_BOX, BULLET, TAG, ANCHOR, \
	HEADING, PARAGRAPH, BLOCK, NUMBEREDLIST, BULLETLIST, LISTITEM, STRIKE
from zim.tokenparser import TEXT, END, \
	skip_to_end_token, tokens_to_text, tokens_by_line, collect_until_end_token

from zim.plugins.journal import daterange_from_path
	# TODO instead of just importing this function we should define
	#      an interface or hook to call the journal plugin object

logger = logging.getLogger('zim.plugins.tasklist')


from zim.parsing import parse_date as old_parse_date
from .dates import date_re as _raw_parse_date_re
from .dates import parse_date


_tag_re = re.compile(r'(?<!\S)@(\w+)\b', re.U)
_day_re = re.compile(r'(\d{1,2})')
_date_re = re.compile('[<>] ?' + _raw_parse_date_re.pattern + r'|\[d:.+\]')
	# "<" and ">" prefixes for dates, "[d: ...]" for backward compatibility

_MIN_START_DATE = '0'
_MAX_DUE_DATE = '9999' # Constant for empty due date - value chosen for sorting properties
_NO_TAGS = '__no_tags__' # Constant that serves as the "no tags" tag - _must_ be lower case


TASK_STATUS_OPEN = 0		# open checkbox
TASK_STATUS_CLOSED = 1		# closed checkbox OK "v"
TASK_STATUS_CANCELLED = 2	# closed checkbox NOK "x"
TASK_STATUS_MIGRATED = 3	# closed checkbox ">"
TASK_STATUS_TRANSMIGRATED = 4	# closed checkbox "<"

_CHECKBOXES = (CHECKED_BOX, UNCHECKED_BOX, XCHECKED_BOX, MIGRATED_BOX, TRANSMIGRATED_BOX)
TASK_STATUS_BY_BULLET = {
	UNCHECKED_BOX: TASK_STATUS_OPEN,
	CHECKED_BOX: TASK_STATUS_CLOSED,
	XCHECKED_BOX: TASK_STATUS_CANCELLED,
	MIGRATED_BOX: TASK_STATUS_MIGRATED,
	TRANSMIGRATED_BOX: TASK_STATUS_TRANSMIGRATED
}

# position of fiels in tag record as used by parser
_t_status=0
_t_prio=1
_t_waiting=2
_t_start=3
_t_due=4
_t_tags=5
_t_desc=6


def _parse_task_labels(string):
	if string is None:
		return []
	else:
		labels = [s.strip() for s in string.replace(',', ' ').split()]
		return [l for l in labels if l]


def _task_labels_re(labels, flags=0):
	return re.compile(
		r'^(' + '|'.join(re.escape(l.strip(':')) for l in labels) + r')(?!\w)',
		flags=flags
	)

def _parse_page_list(input):
	paths = []
	if not input or not input.strip():
		return paths

	for name in input.split(','):
		try:
			paths.append(Path(Path.makeValidPageName(name.strip())))
		except ValueError:
			logger.warning('Could not parse page name: "%s"', name)
	return paths


class TasksIndexer(IndexerBase):
	'''Indexer that gets added to the L{Index} to keep track of tasks
	in the database
	'''

	PLUGIN_NAME = "tasklist"
	PLUGIN_DB_FORMAT = "0.9"

	INIT_SCRIPT = '''
		CREATE TABLE IF NOT EXISTS tasklist (
			id INTEGER PRIMARY KEY,
			source INTEGER,
			parent INTEGER,
			haschildren BOOLEAN,
			hasopenchildren BOOLEAN,
			status INTEGER,
			prio INTEGER,
			waiting BOOLEAN,
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
			waiting_label_re=_task_labels_re(
				_parse_task_labels(
					properties['waiting_labels']), re.IGNORECASE),
			nonactionable_tags=tuple(
				t.strip('@').lower()
					for t in _parse_task_labels(properties['nonactionable_tags'])),
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
				opts['default_start_date'] = date[1].isoformat()
				opts['daterange'] = (date[1], date[2])
			elif date and self.integrate_with_journal == 'due':
				opts['default_due_date'] = date[2].isoformat()
				opts['daterange'] = (date[1], date[2])

		tasks = self.parser.parse(doc.iter_tokens(), **opts)
		c = self.db.cursor()
		count = c.rowcount
		self._insert_tasks(c, row['id'], 0, tasks)
		if changes or c.rowcount > count:
			self.emit('tasklist-changed')

	def _insert_tasks(self, db, pageid, parentid, tasks):
		# Helper function to insert tasks in table
		for task, children in tasks:
			task[_t_tags] = ','.join(sorted(task[_t_tags])) # make tag list a string
			db.execute(
				'INSERT INTO tasklist(source, parent, haschildren, hasopenchildren, status, prio, waiting, start, due, tags, description)'
				'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
				(pageid, parentid, bool(children), any(c[0][_t_status] == TASK_STATUS_OPEN for c in children)) + tuple(task)
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


class AllTasks(IndexView):
	'''Database "view" that shows tasks that are indexed'''

	_sql_filter = ''
	_include_not_started = True

	STYLE = 'default'

	def __init__(self, db):
		IndexView.__init__(self, db)
		self._status_sql = '(0)' # TASK_STATUS_OPEN
		self._pages = PagesViewInternal(db)
		self.set_status_included(TASK_STATUS_OPEN)

		# Test the db really has a tasklist
		try:
			db.execute('SELECT * FROM tasklist LIMIT 1')
		except sqlite3.OperationalError:
			raise ValueError('No tasklist in index')

	def set_status_included(self, *status):
		assert isinstance(status, tuple) and all(isinstance(s, int) for s in status)
		self.status = status
		if len(status) == 0:
			self._status_sql = '(9999)' # ensure no match
		else:
			self._status_sql = '(%i)' % status if len(status) == 1 else repr(status)
				# prevent "(0,)" in sql - trailing "," causes error

	def __iter__(self):
		return self.list_tasks()

	def list_tasks(self, parent=None, _sql_filter=None, _include_not_started=None):
		'''List tasks
		@param parent: the parent task (as returned by this method) or C{None} to list
		all top level tasks
		@param _sql_filter: sql snippet, defaults to class attribute - private param used by sub-classes, do not use elsewhere
		@param _include_not_started: boolean, defaults to class attribute - private param used by sub-classes, do not use elsewhere
		@returns: a iterator of tasks at this level as sqlite Row objects
		'''
		if _sql_filter is None:
			_sql_filter = self._sql_filter # use class attribute

		if _include_not_started is None:
			_include_not_started = self._include_not_started # use class filter

		if parent:
			parentid = parent['id']
		else:
			parentid = 0

		# Sort:
		#  started tasks by prio, due date, page + id to keep order in page
		#  waiting tasks
		#  not-started tasks by start date, ...
		today = str(datetime.date.today())
		for row in self.db.execute('''
			SELECT tasklist.*, pages.name FROM tasklist
			LEFT JOIN pages ON tasklist.source = pages.id
			WHERE tasklist.status in %s and tasklist.parent=? and tasklist.start<=? %s
			ORDER BY tasklist.waiting ASC, tasklist.prio DESC, tasklist.due ASC, pages.name ASC, tasklist.id ASC
			''' % (self._status_sql, _sql_filter), (parentid, today)
		):
			yield row
		if _include_not_started:
			for row in self.db.execute('''
				SELECT tasklist.*, pages.name FROM tasklist
				LEFT JOIN pages ON tasklist.source = pages.id
				WHERE tasklist.status in %s and tasklist.parent=? and tasklist.start>? %s
				ORDER BY tasklist.start ASC, tasklist.waiting ASC, tasklist.prio DESC, tasklist.due ASC, pages.name ASC, tasklist.id ASC
				''' % (self._status_sql, _sql_filter), (parentid, today)
			):
				yield row

	def count_labels_and_tags_pages(self, task_labels, intersect=None):
		'''Get mapping with count of the tasks with given label or tag
		@param task_labels: list of task labels to be parsed
		@param intersect: 2-tuple of labels and tags already selected, will
		return count based on intersecting with this selection
		@returns: 3 maps, one for label count, one for tag count and one for pagenames
		'''
		# TODO more efficient sql-based version of this
		label_filter_func = lambda r: True
		tag_filter_func = lambda r: True
		if intersect:
			if intersect[0]:
				filter_label_re = _task_labels_re(intersect[0])
				label_filter_func = lambda r: bool(filter_label_re.match(r['description']))

			if _NO_TAGS in intersect[1]:
				tag_filter_func = lambda r: not r['tags']
			elif intersect[1]:
				filter_tags = [t.lower() for t in intersect[1]]
				def _tag_filter_func(r):
					tags = r['tags'].lower().split(',')
					return all(t in tags for t in filter_tags)
				tag_filter_func = _tag_filter_func

		task_label_re = _task_labels_re(task_labels)
		labels = {}
		tags = {_NO_TAGS: 0}
		pages = {}
		self._count_rows(None, tag_filter_func, label_filter_func, task_label_re, labels, tags, pages)

		# Remove duplicates by case in tags - keeps version with uppercase due
		# to sorting 2nd element in tuple
		prev_key = ''
		for key in sorted(tags.keys(), key=lambda s: (s.lower(), s)):
			if key.lower() == prev_key.lower():
				tags[prev_key] += tags.pop(key)
			else:
				prev_key = key

		return labels, tags, pages

	def _count_rows(self, parent, tag_filter_func, label_filter_func, task_label_re, labels, tags, pages):
		for row in filter(tag_filter_func, filter(label_filter_func, self.list_tasks(parent))):
			m = task_label_re.match(row['description'])
			if m:
				key = m.group(1)
				if key in labels:
					labels[key] += 1
				else:
					labels[key] = 1

			if row['tags']:
				for tag in row['tags'].split(','):
					if tag in tags:
						tags[tag] += 1
					else:
						tags[tag] = 1
			else:
				tags[_NO_TAGS] += 1

			for part in row['name'].split(':'):
				if part in pages:
					pages[part] += 1
				else:
					pages[part] = 1

			if row['haschildren']:
				self._count_rows(row, tag_filter_func, label_filter_func, task_label_re, labels, tags, pages)
				# recurs

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


class ActiveTasks(AllTasks):
	# Active tasks are all tasks that
	# - Have status "open"
	# - Do not have any open children
	# - Do not have a start date in the future
	# - Are not labelled "waiting"

	_include_not_started = False

	def set_status_included(self, *status):
		pass # ignore - keep default on TASK_STATUS_OPEN

	def list_tasks(self, parent=None):
		'''List tasks
		@param parent: the parent task (as returned by this method) or C{None} to list
		all top level tasks
		@returns: a list of tasks at this level as sqlite Row objects
		'''
		if parent:
			return AllTasks.list_tasks(parent)

		# Sort:
		#  started tasks by prio, due date, page + id to keep order in page
		#  waiting tasks
		#  not-started tasks by start date, ...
		today = str(datetime.date.today())
		for row in self.db.execute('''
			SELECT tasklist.*, pages.name FROM tasklist
			LEFT JOIN pages ON tasklist.source = pages.id
			WHERE tasklist.status=0 and tasklist.start<=? and hasopenchildren=0 and waiting=0 %s
			ORDER BY tasklist.waiting ASC, tasklist.prio DESC, tasklist.due ASC, pages.name ASC, tasklist.id ASC
			''' % self._sql_filter, (today,)
		):
			yield row
		if self._include_not_started:
			for row in self.db.execute('''
				SELECT tasklist.*, pages.name FROM tasklist
				LEFT JOIN pages ON tasklist.source = pages.id
				WHERE tasklist.status=0 and tasklist.start>? and hasopenchildren=0 and waiting=0 %s
				ORDER BY tasklist.start ASC, tasklist.waiting ASC, tasklist.prio DESC, tasklist.due ASC, pages.name ASC, tasklist.id ASC
				''' % self._sql_filter, (today,)
			):
				yield row


class NextActionTasks(ActiveTasks):
	# Like ActiveTasks but in addition:
	#  - Either prio, due date or parent must be defined (else it is an inbox item)
	#  - No children (open or closed) (else it is a project)

	# TODO use _sql_filter attribute more effectively'
	_include_not_started = False

	def list_tasks(self, parent=None):
		today = str(datetime.date.today())
		for row in ActiveTasks.list_tasks(self):
			if (row['parent'] != 0 or row['prio'] > 0 or row['due'] != _MAX_DUE_DATE) \
				and not row['haschildren'] and row['start'] <= today:
					yield row
			else:
				pass


class InboxTasks(ActiveTasks):
	# Like ActiveTasks but:
	#  - No prio, due date or parent (else it is in next actions)
	#  - No children (open or closed) (else it is a project)

	# TODO use _sql_filter attribute more effectively
	_include_not_started = False

	STYLE = 'inbox'

	def list_tasks(self, parent=None):
		today = str(datetime.date.today())
		for row in ActiveTasks.list_tasks(self):
			if row['parent'] == 0 and not row['haschildren'] and row['prio'] == 0 \
				and row['due'] == _MAX_DUE_DATE and row['start'] <= today:
					yield row
			else:
				pass


class OpenProjectsTasks(AllTasks):
	# All open tasks that have children
	# For top level requires status=TASK_STATUS_OPEN, while children follow
	# general selection

	def list_tasks(self, parent=None):
		if parent:
			return AllTasks.list_tasks(self, parent)
		else:
			return AllTasks.list_tasks(self, _sql_filter='and status=0 and haschildren=1', _include_not_started=False)




class WaitingTasks(AllTasks):
	# All tasks that have status open and labelled as waiting

	_status_sql = '(0)' # TASK_STATUS_OPEN
	_include_not_started = False

	STYLE = 'waiting'

	def set_status_included(self, *status):
		pass # ignore - keep default on TASK_STATUS_OPEN

	def list_tasks(self, parent=None):
		if parent:
			return AllTasks.list_tasks(self, parent)
		else:
			seen = set()
			for row in self._list_all(_sql_filter='and waiting', _include_not_started=self._include_not_started):
				seen.add(row['id'])
				if row['parent'] not in seen:
					yield row

	def _list_all(self, _sql_filter, _include_not_started):
		# TODO: code copied from AllTasks.list_tasks(), but without parent id
		#      - refactor to keep in one place ?
		#
		# Sort:
		#  started tasks by prio, due date, page + id to keep order in page
		#  not-started tasks by start date, ...
		today = str(datetime.date.today())
		for row in self.db.execute('''
			SELECT tasklist.*, pages.name FROM tasklist
			LEFT JOIN pages ON tasklist.source = pages.id
			WHERE tasklist.status in %s and tasklist.start<=? %s
			ORDER BY tasklist.prio DESC, tasklist.due ASC, pages.name ASC, tasklist.id ASC
			''' % (self._status_sql, _sql_filter), (today,)
		):
			yield row
		if _include_not_started:
			for row in self.db.execute('''
				SELECT tasklist.*, pages.name FROM tasklist
				LEFT JOIN pages ON tasklist.source = pages.id
				WHERE tasklist.status in %s and tasklist.start>? %s
				ORDER BY tasklist.start ASC, tasklist.prio DESC, tasklist.due ASC, pages.name ASC, tasklist.id ASC
				''' % (self._status_sql, _sql_filter), (today,)
			):
				yield row


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
			waiting_label_re=_task_labels_re(['Waiting'], re.IGNORECASE),
			nonactionable_tags=(),
			all_checkboxes=True,
	):
		self.task_label_re = task_label_re
		self.waiting_label_re = waiting_label_re
		self.nonactionable_tags = nonactionable_tags
		self.all_checkboxes = all_checkboxes

	def parse(self, tokens, default_start_date=_MIN_START_DATE, default_due_date=_MAX_DUE_DATE, daterange=None):

		defaults = [0, 0, False, default_start_date, default_due_date, []]
					# [0:status, 1:prio, 2:waiting, 3:start, 4:due, 5:tags]
		default_defaults = defaults[:]
		heading_level_set_date = None

		tasks = []
		token_iter = iter(tokens)

		check_list_heading = False
		for t in token_iter:
			if t[0] == HEADING:
				# Parse task and day from heading.
				task, day = self._parse_heading(token_iter, daterange)
				if task:
					tasks.append(task)
					# TODO: shouldn't we recurs and consider tasks in next para as sub-tasks ? Reset at next heading

				if day:
					# Respect start or due date properties.
					if defaults[3] != _MIN_START_DATE:
						defaults[3] = day
					elif defaults[4] != _MAX_DUE_DATE:
						defaults[4] = day
					heading_level_set_date = t[1]['level']
				elif heading_level_set_date and heading_level_set_date <= t[1]['level']:
					# reset state - in theory this should be a stack, but reset is good enough for now
					defaults = default_defaults[:]
					heading_level_set_date = None
				else:
					pass # keep defaults as is
			elif t[0] == PARAGRAPH:
				paratasks = self._parse_paragraph(token_iter, defaults)
				check_list_heading = (len(paratasks) == 1) # Para should be single line -- ### TODO that is not strictly tested here!
				tasks.extend(paratasks)
			elif t[0] in (BULLETLIST, NUMBEREDLIST):
				if check_list_heading and self._is_list_heading(tasks[-1]):
					heading = tasks.pop()
					mydefaults = heading[0]
					check_labels = False
				else:
					mydefaults = defaults
					check_labels = not self.all_checkboxes

				listtasks = self._parse_list(token_iter, defaults=mydefaults, check_labels=check_labels)
				tasks.extend(listtasks)
				check_list_heading = False
			else:
				check_list_heading = False
				continue # Skip other toplevel content

		return tasks

	def _is_list_heading(self, task):
		text = task[0][_t_desc]
		if self.task_label_re.match(''.join(text)):
			# strip tags, dates & prio marks
			text = _date_re.sub('', text)
			text = text.replace('!', '')
			words = text.strip().split()
			return all(w.startswith('@') for w in words[1:])
		else:
			return False

	def _parse_heading(self, token_iter, daterange):
		head = collect_until_end_token(token_iter, HEADING)

		if daterange:
			day = self._parse_heading_day(head, daterange)
		else:
			day = None

		if self._starts_with_label(head):
			fields = self._task_from_tokens(head)
			return (fields, []), day
		else:
			return None, day

	def _parse_heading_day(self, tokens, daterange):
		# Check for date string in heading anchor ids. Only use it if it is a
		# date within daterange to avoid false positives. First match in left
		# to right parsing is used.
		for t in tokens:
			if t[0] == ANCHOR:
				try:
					date = parse_date(t[1]['name'])
				except ValueError:
					continue
				else:
					if date >= daterange[0] and date <= daterange[1]:
						return date.isoformat()
					else:
						continue
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
		# Look for lines that define tasks
		paragraph = collect_until_end_token(token_iter, PARAGRAPH)
		tasks = []

		for line in tokens_by_line(paragraph):
			if self._starts_with_label(line):
				fields = self._task_from_tokens(line, defaults=defaults)
				tasks.append((fields, []))
			else:
				pass

		return tasks

	def _parse_list(self, token_iter, defaults=None, check_labels=False):
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

				if (not check_labels and bullet in _CHECKBOXES)\
				or self._starts_with_label(line):
					fields = self._task_from_tokens(
						line,
						status=TASK_STATUS_BY_BULLET.get(bullet, TASK_STATUS_OPEN),
						defaults=defaults
					)
					tasks.append((fields, []))
					parent_item = tasks[-1]
				else:
					parent_item = None
						# Since this line is not a task, sub-items will be added to top level list

				if next_token[0] in (BULLETLIST, NUMBEREDLIST):
					# Sub-list
					if parent_item:
						mytasks = self._parse_list(token_iter, defaults=parent_item[0], check_labels=check_labels) # recurs
						parent_item[-1].extend(mytasks)
						if any(t[0][_t_status] == TASK_STATUS_OPEN for t in mytasks):
							parent_item[0][_t_status] = TASK_STATUS_OPEN # Force parent open if any child is
					else:
						mytasks = self._parse_list(token_iter, defaults=defaults, check_labels=check_labels) # recurs
						tasks.extend(mytasks)

					next_token = next(token_iter)
					if not next_token == (END, LISTITEM):
						logger.warning('Unexpected token in list: %r', next_token)

			elif t[0] == END and t[1] in (BULLETLIST, NUMBEREDLIST):
				break
			else:
				logger.warning('Unexpected token in list: %r', t)

		return tasks

	def _task_from_tokens(self, tokens, status=0, defaults=None):
		# Collect text and returns task

		text = []
		tags = set(defaults[_t_tags]) if defaults else set() # copy

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

		return self._task_from_text(''.join(text), status, tags, defaults)

	def _task_from_text(self, text, status, tags, defaults=None):
		# Return task record for single line of text

		prio = text.count('!')
		start, due = _MIN_START_DATE, _MAX_DUE_DATE
		waiting = bool(self.waiting_label_re.match(text.lstrip())) \
					or any(t in tags for t in self.nonactionable_tags)

		if defaults:
			if prio == 0:
				prio = defaults[_t_prio] # inherit prio
			start = defaults[_t_start] # inherit start date
			due = defaults[_t_due] # inherit due date

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
					logger.warning('False positive matching date: %s', string)
			except ValueError:
				logger.warning('Invalid date format in task: %s', string)

		return [status, prio, waiting, start, due, tags, str(text.strip())]
			# 0:status, 1:prio, 2:waiting, 3:start, 4:due, 5:tags, 6:desc


import re
from glob import glob

from tests import TestCase

class TestTranslations(TestCase):

	def runTest(self, verbose=False):
		'''Sanity check translation files'''
		for file in ['translations/zim.pot'] + glob('translations/*.po'):
			if verbose:
				print 'Checking %s' % file
			t = TranslationFile(file)
			if not file.endswith('.pot'):
				assert t.nplural > 0, 'Missing number of plurals: %s' % file
			t.assertValid()


class TranslationMessage(object):

	@property
	def nplural(self):
		return len(self.msgstr)

	def __init__(self, lineno, text):
		self.lineno = lineno
		self.msgid = None
		self.msgid_plural = None
		self.msgstr = []
		self.comment = ''

		text = text.replace('"\n"', '')
		for line in text.splitlines():
			if line.startswith('#'):
				self.comment += line
			else:
				type, msg = line.split(' ', 1)
				if type == 'msgid':
					self.msgid = msg
				elif type == 'msgid_plural':
					self.msgid_plural = msg
				elif type.startswith('msgstr'):
					self.msgstr.append(msg)
				else:
					raise AssertionError, \
					'Could not parse line: %s %s' % (type, msg)

		assert self.msgid, 'No msgid found'
		assert self.msgstr, 'No msgstr found'


	_format_string_re = re.compile('%.')

	def check_nplural(self, nplural):
		if self.msgid_plural and self.msgstr[0] != '""':
			return self.nplural == nplural
		else:
			return True

	def check_format_strings(self):
		'''Check format strings in msgid_plural and msgstr'''
		if 'strftime' in self.comment:
			return True # strftime format string

		wanted = sorted( self._format_string_re.findall(self.msgid) )
		if not wanted:
			return True # no string format used

		for msg in [self.msgid_plural] + self.msgstr:
			if msg and not msg == '""':
				got = sorted( self._format_string_re.findall(msg) )
				if not got == wanted:
					return False
		else:
			return True


class TranslationFile(object):

	def __init__(self, file):
		self.file = file
		self.messages = []

		buffer = []
		lineno = 0
		msgidlineno = 0
		def flush():
			if not buffer \
			or all(line.startswith('#') for line in buffer):
				return

			try:
				text = ''.join(buffer)
				message = TranslationMessage(msgidlineno, text)
				self.messages.append(message)
			except AssertionError, error:
				raise AssertionError, \
				'Error while parsing %s msgid on line %i\n' % (self.file, msgidlineno) + error.message

		for line in open(file):
			lineno += 1
			if not line or line.isspace():
				flush()
				buffer = []
			else:
				if line.startswith('msgid '):
					msgidlineno = lineno
				buffer.append(line)
		else:
			flush()

		plural_forms = self.headers['Plural-Forms']
		m = re.search(r'nplurals=(\d+);', plural_forms)
		if m:
			self.nplural = int( m.group(1) )
		else:
			self.nplural = None

	@property
	def headers(self):
		message = self.get('""')
		lines = message.msgstr[0].strip().strip('"').split('\\n')
		headers = {}
		for line in lines:
			if not line:
				continue
			k, v = line.strip('"').replace('\\n', '').split(': ', 1)
			headers[k] = v
		return headers

	def get(self, msgid):
		for message in self.messages:
			if message.msgid == msgid:
				return message
		else:
			return None

	def assertValid(self):
		for message in self.messages:
			if self.nplural and not message.check_nplural(self.nplural):
				raise AssertionError, \
				'Number of plural forms NOK in %s msgid on line %i\n' % (self.file, message.lineno) + message.msgid

			if not message.check_format_strings():
				raise AssertionError, \
				'Error with format strings in %s msgid on line %i\n' % (self.file, message.lineno) + message.msgid


if __name__ == '__main__':
	TestTranslations().runTest(verbose=True)

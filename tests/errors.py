
from __future__ import with_statement

from tests import TestCase

from zim.errors import *

text = '''\
Error 6

Some description
here
'''

class TestErrors(TestCase):

	def runTest(self):
		'''Check base class for errors'''
		self.assertEqual(str(StubError(6)), text)
		self.assertEqual(unicode(StubError(6)), text)


class StubError(Error):
	description = '''\
Some description
here
'''

	def __init__(self, i):
		self.msg = 'Error %i' % i


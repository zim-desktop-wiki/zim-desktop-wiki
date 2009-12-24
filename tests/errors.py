
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


class TestSignalContext(TestCase):

	def runTest(self):
		'''Test catching exceptions in signals'''
		
		object = MockGObject()
		
		def emit(doraise):
			with SignalExceptionContext(object, 'foo'):
				return object.emit('foo', doraise)
		
		self.assertRaises(StubError, emit, True)

		self.assertTrue(emit(False)) # test we can run without exception...


class MockGObject(object):

	def emit(self, signal, doraise):
		try:
			with SignalRaiseExceptionContext(self, signal):
				if doraise:
					raise StubError, 42
				else:
					pass
		except:
			pass # ignore all errors
		return True

	def stop_emission(self, name):
		pass

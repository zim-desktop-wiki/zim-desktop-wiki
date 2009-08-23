
from tests import TestCase, get_test_data_page, get_test_page

from zim.fs import *
from zim.formats import wiki
from zim.gui.pageview import *

class TestTextBuffer(TestCase):

	# TODO test that raw parsetree is really raw - so test that
	# buffer.get_parstree(raw=True) provides roundtrip the other
	# way, so formatting with "errors" reproduces exactly the same after
	# reloading the raw parsetree

	def runTest(self):
		'''Test serialization of the page view textbuffer'''
		wikitext = get_test_data_page('wiki', 'roundtrip')
		tree = wiki.Parser().parse(wikitext)
		notebook, page = get_test_page()
		notebook.get_store(page).dir = Dir('/foo') # HACK
		tree.resolve_images(notebook, page)
		buffer = TextBuffer()
		buffer.set_parsetree(tree)
		result = buffer.get_parsetree()
		#~ print result.tostring()
		#~ self.assertEqualDiff(result.tostring(), tree.tostring())
		result = u''.join(wiki.Dumper().dump(result))
		self.assertEqualDiff(result, wikitext)



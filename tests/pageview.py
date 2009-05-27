
from tests import TestCase, get_test_data, get_test_page

from zim.fs import *
from zim.formats import wiki
from zim.gui.pageview import *

class TestTextBuffer(TestCase):

	def runTest(self):
		wikitext = get_test_data('notebook-wiki/roundtrip.txt')
		tree = wiki.Parser().parse(wikitext)
		notebook, page = get_test_page()
		notebook.get_store(page).dir = Dir('/foo') # HACK
		tree.resolve_images(notebook, page)
		#~ print tree.tostring()
		buffer = TextBuffer()
		buffer.set_parsetree(tree)
		tree = buffer.get_parsetree()
		#~ print tree.tostring()
		result = u''.join(wiki.Dumper().dump(tree))
		self.assertEqualDiff(result, wikitext)

# TODO: Licence Header and Copyright

'''This modules handles export of LaTeX Code'''


from zim.formats import *
from zim.parsing import TextBuffer

info = {
	'name':		'LaTeX',
	'mime': 	'application/x-tex',
	'extension': 'tex',
	'read':		False,
	'write':	False,
	'import':	False,
	'export':	True,
}

bullets = {
	'\\item[\\Square] ': UNCHECKED_BOX,
	'\\item[\\XBox] ': XCHECKED_BOX,
	'\\item[\CheckedBox] ': CHECKED_BOX,
	'\\item ': BULLET,
}
# reverse dict
bullet_types = {}
for bullet in bullets:
	bullet_types[bullets[bullet]] = bullet

class Dumper(DumperClass):

	def dump(self, tree):
		assert isinstance(tree, ParseTree)
		output = TextBuffer()
		self.dump_children(tree.getroot(),output)
		return output.get_lines()

	def dump_children(self, list, output, list_level = -1):
		if list.text:
			output.append(list.text)

		for element in list.getchildren():
			if element.tag == 'p':
				if 'indent' in element.attrib:
					indent = int(element.attrib['indent'])
				else:
					indent = 0
				myoutput = TextBuffer()
				self.dump_children(element,myoutput)
				if indent:
					myoutput.prefix_lines('\t'*indent)
				output.extend(myoutput)
			elif element.tag == 'ul':
				output.append('\\begin{itemize}\n')
				self.dump_children(element,output,list_level=list_level+1)
				output.append('\\end{itemize}')
			elif element.tag == 'h':
				level = int(element.attrib['level'])
				if level < 1: level = 1
				elif level > 5: level = 5
				if   level == 1: output.append('\\chapter{'+element.text+'}')
				elif level == 2: output.append('\\section{'+element.text+'}')
				elif level == 3: output.append('\\subsection{'+element.text+'}')
				elif level == 4: output.append('\\subsubsection{'+element.text+'}')
				elif level == 4: output.append('\\paragraph{'+element.text+'}')
			elif element.tag == 'li':
				if 'indent' in element.attrib:
					list_level = int(element.attrib['indent'])
				if 'bullet' in element.attrib:
					bullet = bullet_types[element.attrib['bullet']]
				else:
					bullet = '\\item '
				output.append('\t'*list_level+bullet)
				self.dump_children(element, output, list_level=list_level) # recurs
				output.append('\n')
			elif element.tag == 'pre':
				output.append('\n\\begin{verbatim}\n')
				output.append(text.element)
				output.append('\n\\end{verbatim}\n')
			elif element.tag == 'img':
				#TODO: Handle images
				pass
			elif element.tag == 'link':
				#TODO: Handle links with hyperref
				pass
			elif element.tag == 'emphasis':
				output.append('\\emph{'+element.text+'}')
			elif element.tag == 'strong':
				output.append('\\textbf{'+element.text+'}')
			elif element.tag == 'mark':
				output.append('\\underline{'+element.text+'}')
			elif element.tag == 'strike':
				output.append('\\sout{'+element.text+'}')
			elif element.tag == 'code':
				success = false
				for delim in '+*|$&%!-_':
					if not delim in element.text:
						success = true
						output.append('\\verb'+delim+element.text+delim)
				if not success:
					assert False, 'Found no suitable delimiter for verbatim text: %s' % element
					pass
			else:
				assert False, 'Unknown node type: %s' % element

			if element.tail:
				output.append(element.tail)

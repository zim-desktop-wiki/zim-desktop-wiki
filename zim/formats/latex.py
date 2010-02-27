# TODO: Licence Header and Copyright

'''This modules handles export of LaTeX Code'''


from zim.formats import *
from zim.parsing import TextBuffer, url_re

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
	'\\item[\\CheckedBox] ': CHECKED_BOX,
	'\\item ': BULLET,
}
# reverse dict
bullet_types = {}
for bullet in bullets:
	bullet_types[bullets[bullet]] = bullet

def tex_encode(text):
	if not text is None:
		#TODO: non-hacky solution
		text = text.replace('\\','SOMETHINGWHICHIHOPEWILLNEVERTURNUPINATEXTOTHERWISETHISWILLSCREWUP')
		text = text.replace('&','\\&')
		text = text.replace('$','\\$ ')
		text = text.replace('^','\\^{}')
		text = text.replace('%','\\%')
		text = text.replace('#','\\# ')
		text = text.replace('_', '\\_')
		text = text.replace('SOMETHINGWHICHIHOPEWILLNEVERTURNUPINATEXTOTHERWISETHISWILLSCREWUP','$\\backslash$')
		return text
	else:
		return ''

class Dumper(DumperClass):

	def dump(self, tree):
		assert isinstance(tree, ParseTree)
		assert self.linker, 'HTML dumper needs a linker object'
		self.linker.set_usebase(True)
		output = TextBuffer()
		self.dump_children(tree.getroot(),output)
		return output.get_lines()

	def dump_children(self, list, output, list_level = -1):
		if list.text:
			output.append(tex_encode(list.text))

		for element in list.getchildren():
			text = tex_encode(element.text)
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
				if   level == 1: output.append('\\chapter{'+text+'}')
				elif level == 2: output.append('\\section{'+text+'}')
				elif level == 3: output.append('\\subsection{'+text+'}')
				elif level == 4: output.append('\\subsubsection{'+text+'}')
				elif level == 4: output.append('\\paragraph{'+text+'}')
			elif element.tag == 'li':
				if 'indent' in element.attrib:
					list_level = int(element.attrib['indent'])
				if 'bullet' in element.attrib:
					bullet = bullet_types[element.attrib['bullet']]
				else:
					bullet = '\\item '
				output.append('\t'*list_level+bullet)
				self.dump_children(element, output, list_level=list_level) # recurse
				output.append('\n')
			elif element.tag == 'pre':
				output.append('\n\\begin{verbatim}\n')
				output.append(element.text)
				output.append('\n\\end{verbatim}\n')
			elif element.tag == 'img':
				output.append('\\includegraphics{%s}'% self.linker.link(element.attrib['src']))
				#TODO: Handle options
			elif element.tag == 'link':
				href = self.linker.link(element.attrib['href'])
				output.append('\\href{%s}{%s}' % (href, text))
			elif element.tag == 'emphasis':
				output.append('\\emph{'+text+'}')
			elif element.tag == 'strong':
				output.append('\\textbf{'+text+'}')
			elif element.tag == 'mark':
				output.append('\\underline{'+text+'}')
			elif element.tag == 'strike':
				output.append('\\sout{'+text+'}')
			elif element.tag == 'code':
				success = False
				for delim in '+*|$&%!-_':
					if not delim in text:
						success = True
						output.append('\\verb'+delim+text+delim)
				if not success:
					assert False, 'Found no suitable delimiter for verbatim text: %s' % element
					pass
			else:
				assert False, 'Unknown node type: %s' % element

			if element.tail:
				output.append(tex_encode(element.tail))

# -*- coding: utf-8 -*-

# Copyright 2009 Pablo Angulo

'''Script to export zim wiki pages to trac / mediawiki

To use it, call

	python trac2zim.py notebook output_folder prefix

where prefix is a string you put before each wiki page name. It will
fill output_folder with plain text files ready to be loaded with trac-admin:

	trac-admin /path/to/project wiki load output_folder

zim links like [[:Software:note taking:zim|zim]] are flattened to wiki
entries like [Software_note_taking_zim zim].
'''

import re
import sys
import os

#buscaCabeceras=re.compile('(={1:5})([^=]*)(={1:5})')
def flatten(linkName):
	'''Changes a zim link, possibly with categories, to a trac link

	it also removes accents and other spanish special characters
	'''
	#remove final ':' character and
	name=linkName[:-1] if linkName[-1]==':' else linkName
	return removeSpecialChars(name.replace(':','_').replace(' ','_'))

def removeSpecialChars(s):
	'''certain trac installation reported problems with special chars

	other trac systems loaded all files without problem

	the problem is only for file names and wiki pages names, not for content
	'''
	return s.replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ñ','n').replace('Á','A').replace('É','E').replace('Í','I').replace('Ó','O').replace('Ú','U').replace('Ñ','ñ')

cabecera=re.compile("(={1,6})([^=\/]+?)(={1,6})")
inlineVerbatim=re.compile("''([^']+?)''")
#~ multilineVerbatim=re.compile("\n[\t](.+?)\n")
negrita=re.compile('\*\*([^\*]+?)\*\*')
italic=re.compile('\/\/([^\/\n\]]+?)\/\/')
bracketedURL=re.compile('\[\[(http:\/\/[^\|]+)\|([^\|]+?)\]\]')
#TODO: separar links relativos y absolutos
simpleRelLink=re.compile('\[\[([^:][^\|]+?)\]\]')
namedRelLink=re.compile('\[\[([^:][^\|]+?)\|([^\|]+?)\]\]')
simpleAbsLink=re.compile('\[\[:([^\|]+?)\]\]')
namedAbsLink=re.compile('\[\[:([^\|]+?)\|([^\|]+?)\]\]')
images=re.compile('([^\{])\{\{\/(.+?)\}\}')
def translate(nota,prefix1,prefix2):
	'''Takes a note in zim format and returns a note in trac format
	'''
	#duplicate all line breaks
	nota=nota.replace('\n','\n\n')
	# Headings
	mm=cabecera.search(nota)
	lista=[]
	lastIndex=0
	while mm:
		lista.append(nota[lastIndex:mm.start()])
		gg=mm.groups()
		iguales=len(gg[0])
		lista.append("="*(7-iguales)+gg[1]+"="*(7-iguales))
		lastIndex=mm.end()
		mm=cabecera.search(nota,lastIndex)
	lista.append(nota[lastIndex:])
	nota=''.join(lista)

	#inlineVerbatim
	nota=inlineVerbatim.sub("{{{\\1}}}",nota)
	#multiline verbatim
	#TODO
	#bold
	nota=negrita.sub("'''\\1'''",nota)
	#italic
	nota=italic.sub("''\\1''",nota)

	#bracketedURL
	nota = bracketedURL.sub("[\\1 \\2]",nota)
	#~ #simple links
	#~ nota=simpleLink.sub("[wiki:\\1]",nota)
	#~ #named links
	#~ nota=namedLink.sub("[wiki:\\1 \\2]",nota)
	#simple relative links
	mm=simpleRelLink.search(nota)
	lista=[]
	lastIndex=0
	while mm:
		lista.append(nota[lastIndex:mm.start()])
		gg0=mm.groups()[0]
		lista.append("[wiki:"+prefix1+prefix2+flatten(gg0)+" "+gg0+"]")
		lastIndex=mm.end()
		mm=simpleRelLink.search(nota,lastIndex)
	lista.append(nota[lastIndex:])
	nota=''.join(lista)

	mm=simpleAbsLink.search(nota)
	lista=[]
	lastIndex=0
	while mm:
		lista.append(nota[lastIndex:mm.start()])
		gg0=mm.groups()[0]
		lista.append("[wiki:"+prefix1+flatten(gg0)+" "+gg0+"]")
		lastIndex=mm.end()
		mm=simpleAbsLink.search(nota,lastIndex)
	lista.append(nota[lastIndex:])
	nota=''.join(lista)

	#named relativelinks
	mm=namedRelLink.search(nota)
	lista=[]
	lastIndex=0
	while mm:
		lista.append(nota[lastIndex:mm.start()])
		gg=mm.groups()
		lista.append("[wiki:"+prefix1+prefix2+flatten(gg[0])+" "+gg[1]+"]")
		lastIndex=mm.end()
		mm=namedRelLink.search(nota,lastIndex)
	lista.append(nota[lastIndex:])
	nota=''.join(lista)

	#named absolute links
	mm=namedAbsLink.search(nota)
	lista=[]
	lastIndex=0
	while mm:
		lista.append(nota[lastIndex:mm.start()])
		gg=mm.groups()
		lista.append("[wiki:"+prefix1+flatten(gg[0])+" "+gg[1]+"]")
		lastIndex=mm.end()
		mm=namedAbsLink.search(nota,lastIndex)
	lista.append(nota[lastIndex:])
	nota=''.join(lista)

	#lists
	nota=nota.replace('\n* ','\n * ')

	#images
	nota=images.sub("\\1[[Image(\\2)]]",nota)

	return nota

def processPath(pathin,pathout,prefix1,prefix2=''):
	for archivo in os.listdir(pathin):
		fullPath=os.path.join(pathin,archivo)
		if archivo[-3:]=='txt':
			fichero=open(fullPath,mode='r')
			nota=fichero.read()
			fichero.close()

			nota_out=translate(nota,prefix1,prefix2)

			#~ nameout= prefix+"_"+archivo[:-4] if prefix else archivo[:-4]

			fichero=open(os.path.join(pathout,prefix1+prefix2+removeSpecialChars(archivo[:-4])),mode='w')
			fichero.write(nota_out)
			fichero.close()
		elif os.path.isdir(fullPath):
			print pathin,archivo,fullPath

			processPath(fullPath,pathout,prefix1,prefix2+removeSpecialChars(archivo)+"_")

if __name__=='__main__':

	pathin=sys.argv[1]
	pathout=sys.argv[2]
	prefix=sys.argv[3]

	processPath(pathin,pathout,prefix)

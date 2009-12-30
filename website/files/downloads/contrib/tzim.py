#!/usr/bin/python
#################################################################################################
#                                                                                               #
# tzim.py - Simple conversion module to convert a Tomboy notes database to zim format.          #
#           _Usage_:                                                                            #
#           If not alraeady executable,                                                         #
#           $ chmod a+x tzim.py                                                                 #
#           cd to target directory, i.e. where the zim notes shall appear (for example          #
#           to ~/.zim). Run                                                                     #
#           $ <dir-path to tzim.py>/tzim.py                                                     #
#           follow instructions. When conversed, open zim and add repository (i.e. current dir) #
#                                                                                               #
#           Please send notes that failed to convert to bengt at blafs com.                     #
#                                                                                               #
#           GPL statement:                                                                      #
#           This program is free software; you can redistribute it and/or modify                #
#           it under the terms of the GNU General Public License as published by                #
#           the Free Software Foundation; either version 3 of the License, or                   #
#           (at your option) any later version.                                                 #
#                                                                                               #
#           This program is distributed in the hope that it will be useful,                     #
#           but WITHOUT ANY WARRANTY; without even the implied warranty of                      #
#           MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the                       #
#           GNU General Public License for more details.                                        #
#                                                                                               #
#           You should have received a copy of the GNU General Public License                   #
#           along with this program.  If not, see <http://www.gnu.org/licenses/>.               #
#                                                                                               #
#           Copyright 2007,2008 Bengt J. Olsson                                                 #
#                                                                                               #
# Rev:      1.1                                                                                 #
# Date:     2008-03-08                                                                          #
# Changes:  Fixed a number of issues where the script hanged. Now displays both "Last changed"  #
#           and "Create date" (if these exists) and conversion date. Added a few character subs.#
#           Some clean-up of the code.                                                          #
# Filename: tzim.py                                                                             #
# Rev:      1.0                                                                                 #
# Date:     2007-07-28                                                                          #
# Changes:  First version                                                                       #
#################################################################################################
import os
import os.path
import sys
import glob
import re
import datetime
# import pdb
def main():
#        pdb.set_trace()
	tomboynotes = raw_input("Path to tomboy notes directory (default ~/.tomboy): ")
	if tomboynotes == "":
		tomboynotes = os.path.expanduser('~')
		tomboynotes += '/.tomboy/'
	if not tomboynotes.rstrip == '/':
		tomboynotes += '/*.note'
	else:
		tomboynotes += '*.note'
	files = glob.glob(tomboynotes)				# Read tomboy notes file names
	if len(files) == 0 :
		print "No note files."				# Exit if no note files in directory
		sys.exit()
	for fil in files:
		infile = open(fil,'r')
		infile.readline() # get rid of first lines in tomboy note
		line = infile.readline()
		if not re.search('note version="0.2"',line):
			print "Only tested with tomboy notes format version 0.2"
		line = infile.readline() # Third line contains title of note
		line = line.rstrip()
		line = re.sub('<\/?title>','',line) # remove <title> and </title>
		line = re.sub('^\s*','',line) # remove heading whitespaces
		line = format(line)
		print "converting note ", line
		outfilename = re.sub(' ','_',line) + '.txt' # zim file name for note
		outfilename = re.sub('[/&<>:;]','_',outfilename) # get rid of "dangerous" chars in filename
		outfile = open(outfilename,'w')	
		line = '====== ' + line + ' ======' + '\n'
		outfile.write(line)
		line = 'Converted from Tomboy: ' + datetime.date.today().strftime("%Y-%m-%d") + '\n\n'
		outfile.write(line)
		line = infile.readline()
		if re.search('</text>$',line):
			line = "</note-content></text>"
		else:
			line = infile.readline()
			if (line == ""):
				line = infile.readline()
			line = format(line)
		while not re.search('</text>$',line):
			outfile.write(line)
			line = infile.readline()
			line = format(line)
		line = re.sub('<\/note-content><\/text>','',line)
		line = format(line)
		outfile.write(line)
		line = infile.readline()
		if (re.search('.*(\d\d\d\d-\d\d-\d\d).*',line)):
			line = re.search('.*(\d\d\d\d-\d\d-\d\d).*',line)
			line = line.group(1)
			line = "\nNote last changed (in Tomboy): " + line + "\n"
			outfile.write(line)
			line = infile.readline()
		if (re.search('.*(\d\d\d\d-\d\d-\d\d).*',line)):
			line = re.search('.*(\d\d\d\d-\d\d-\d\d).*',line)
			line = line.group(1)
			line = "Note created         (in Tomboy): " + line + "\n"
			outfile.write(line)
		infile.close()
		outfile.close()       		

def format(line): 										#various format substitutions of lines
	line = re.sub('</?bold>','**',line)
	line = re.sub('</?italic>','//',line)
	line = re.sub('</?strikethrough>','~~',line)
	line = re.sub('</?highlight>','__',line)
	line = re.sub('</?size:(small|large|huge)>','',line)# Can't handle tomboy sizes
	line = re.sub('</?monospace>','',line)				# or fixed-width
	line = re.sub('<link:(internal|broken)>','[[',line)
	line = re.sub('</link:(internal|broken)>',']]',line)
	line = re.sub('<link:(url)>','',line)
	line = re.sub('</link:(url)>','',line)
	line = re.sub('<list-item dir="ltr">','* ',line)# List handling in tomboy to complexfor this
	line = re.sub('(</?list>|</list-item>)','',line)# this simple converter; generating a one-level
	line = re.sub('&gt;','>',line)					# list only
	line = re.sub('&lt;','<',line) 
	line = re.sub('&amp;','&',line) 
	return(line)
		
main()

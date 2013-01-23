#   Copyright (c) 2010, 2011 Patricio Paez <pp@pp.com.mx>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>

from __future__ import division # We are doing math in this module ...


__doc__ = '''
arithmetic is a Python module that allows mixing arithmetic
operations and text.

Usage as command:

      arithmetic expression(s) Evaluate expression(s).
      arithmetic -f path       Read path contents and evaluate.
      arithmetic               Read from standard input and evaluate.
      arithmetic -h            Show usage

Examples:

      $ arithmetic 2 x 3
      6
      $ echo 4 x 12 | arithmetic
      48
      $ echo 'a = 5    a + 4 =' | arithmetic
      a = 5    a + 4 = 9
      $ arithmetic < filename
      ...

Usage as module:

     from arithmetic import feed
     ...
     resultText = feed( inputText )
     ...
'''

import re


renumber = re.compile( r'([0-9][0-9,]*(\.[0-9]*)?%?)|(\.[0-9]+%?)' )
reidentifier = re.compile( r'[a-zA-Z][a-zA-Z0-9_]*' )
rexenclosed = re.compile( r'[0-9.)](x)[^a-zA-Z]' )

class Lexer:
    ''
    def __init__( self, text ):
        self.text = text
        self.offset = 0

    def gettoken( self ):
        '''Get next token from text and return its type and value.

        Return (None,None) if no more text.

        Identifiers    letter ( letter | digit | _ )*
        Numbers        digit ( digit | , | . ) *
        Operators      - + * / ^ ** x

        x can be a name or an operator

        x preceeded and followed by a digit is taken as if
        preceeded and followed by a space.  i.e 5x3
        is seen as 5 x 3.
        '''
        while self.offset < len( self.text ):
            if self.text[ self.offset ] == ' ':
                value = self.text[ self.offset ]
                self.offset = self.offset + 1
                continue
            if self.text[ self.offset ] == '\n':
                value = self.text[ self.offset ]
                self.offset = self.offset + 1
                self.type = 'r'
                self.value = value
                return
            m = renumber.match( self.text, self.offset )
            if m:
                value = m.group()
                self.offset = m.end()
                self.type = 'f'
                self.value = value
                return
            m = rexenclosed.match( self.text, self.offset - 1 )
            if m:
                value = m.group(1)
                self.offset = m.end(1)
                self.type = 'x'
                self.value = value
                return
            m = reidentifier.match( self.text, self.offset )
            if m:
                value = m.group()
                self.offset = m.end()
                self.type = 'n'
                self.value = value
                return
            if self.text[ self.offset: self.offset + 2 ] == '**':
                value = self.text[ self.offset: self.offset + 2 ]
                self.offset = self.offset + 2
                self.type = 'o'
                self.value = value
                return
            if self.text[ self.offset ] in '+-*/^()':
                value = self.text[ self.offset ]
                self.offset = self.offset + 1
                self.type = 'o'
                self.value = value
                return
            value = self.text[ self.offset ] + '***'
            self.offset = self.offset + 1
            self.type = 'u'
            self.value = value
            return
        self.type = ''
        self.value = None


from decimal import Decimal, getcontext
getcontext().prec = 100


def safe_eval(expression):
	'''Safe evaluation of a python expression'''
	#~ print '>>>', expression
	GLOBALS = {'__builtins__': None} # Don't allow open() etc.
	try:
		re = eval(expression, GLOBALS, {'Decimal': Decimal})
	except Exception, e:
		#~ print e
		raise

	#~ print re
	return re


def evaluate( expression_text, UseDigitGrouping = True, variables = {}, functions = {} ):
    '''Parse expression, calculate and return its result.

    if UseDigitGrouping is True, the result includes commas.

    '''
    expression = []

    lexer = Lexer( expression_text )

    def factor():
        if lexer.value in '-+':
            expression.append( lexer.value )
            lexer.gettoken()
        if lexer.type == 'f':
            #  remove commas and spaces
            #  translate % to /100'''
            value = lexer.value.replace( '%', '' )
            value = value.replace( ' ', '' )
            expression.append( value.replace( ',', '' ) )
            if lexer.value[-1] == '%':
                expression.append( '/' )
                expression.append( '100' )
            lexer.gettoken()
        elif lexer.value == '(':
            expression.append( lexer.value )
            lexer.gettoken()
            expr()
            expression.append( lexer.value )
            lexer.gettoken()
        elif lexer.type == 'n':
            name = lexer.value
            lexer.gettoken()
            # handle multiple word names
            while lexer.type == 'n' and lexer.value != 'x':
                name = name + ' ' + lexer.value
                lexer.gettoken()
            if name in variables:
                # remove commas
                value = variables[ name ].replace( ',', '' )
                expression.append( value )
            elif name in functions:
                if name not in functions[ name ]:
                    # standard formula
                    expression.append( str( evaluate( functions[ name ],
                                       UseDigitGrouping = False,
                                       variables=variables, functions=functions ) ) )
                else:
                    # recurrent relation wihout initial value
                    expression.append( '0' )
            else:
                expression.append( name + ' undefined' )

    def factors():
        if lexer.value == '^' or lexer.value == '**':
            expression.append( '**' )
            lexer.gettoken()
            power()

    def power():
        factor()
        factors()

    def powers():
        if lexer.value and lexer.value in '*x/':
            expression.append( lexer.value.replace( 'x', '*') )
            lexer.gettoken()
            power()
            powers()

    def term():
        power()
        powers()

    def terms():
        if lexer.value and lexer.value in '-+':
            expression.append( lexer.value )
            lexer.gettoken()
            term()
            terms()

    def expr():
        term()
        terms()

    lexer.gettoken()
    expr()

    expressionD = []
    for element in expression:
        if element not in '+-x/^*()' and element != '**':
            element = "Decimal('" + element + "')"
        expressionD.append( element )

    if UseDigitGrouping:
        return AddCommas( safe_eval( ''.join( expressionD ) ) )
    else:
        return safe_eval( ''.join( expressionD ) )



reEqualSign = re.compile( ' ?= ?' )
reSepar = re.compile( '  +|\t' )
reColonLeft = re.compile( ': ' )



def TypeAndValueOf( expression ):
    '''"Returns a (type, value) tuple.

    type may be:

    v = void
    i = integer, f = float
    e = expression containing variables
    a = arithmetic expression, no variables
    n = name

    value is expression with some modifications:
    blank spaces and commas removed, x replaced by *.'''

    lexer = Lexer( expression )

    # Capture the odd token types
    lexer.text = re.sub( '[()]', '', lexer.text )
    lexer.gettoken()
    oddtokens = lexer.type
    while lexer.type:
        lexer.gettoken()
        lexer.gettoken()
        oddtokens = oddtokens + lexer.type

    if oddtokens == '':  # empty
        return 'v', ''
    elif oddtokens == 'f':
        return 'f', expression
    elif oddtokens == 'n':
        return 'n', expression
    elif 'n' in oddtokens or 'x' in oddtokens:
        return 'e', expression  # expression with names
    else:
        return 'a', expression

class Parser:
    'Base class'

    def __init__( self ):
        # Written by parseLine(), read by evaluate():
        self.functions = {}
        self.variables = {}

    def parse( self, text ):
        'Find expresions in text, return it with results.'

        lines = text.splitlines()

        for i in range( self.countLines( lines ) ):
            self.parseLine( i, lines, variables=self.variables, functions=self.functions )

        return '\n'.join( lines )

    def countLines( self, lines ):
        'Return number of lines.'
        return len( lines )

    def readLine( self, i, lines ):
        'Return i line from lines.'
        return lines[i]

    def writeResult( self, i, lines, start, end, text ):
        'Write text in line i of lines from start to end offset.'

        lines[i] = lines[i][ :start ] + text + lines[i][ end: ]

    def parseLine( self, i, lines, variables={}, functions={} ):
            'Find and evaluate expresions in line i.'

            # get line
            line = self.readLine( i, lines )

            RightPrevStart = 0
            RightPrevEnd = 0
            mEqualSignPrev = re.search( '^', line )
            mEqualSignAct = reEqualSign.search( line, mEqualSignPrev.end() )
            while mEqualSignAct:

                # Determine LeftActStart,
                # the larger of mEqualSignPrev, mSeparLeft, mColonLeft, beginofline
                LeftStarts = []
                LeftStarts.append( mEqualSignPrev.end() )

                mSeparLeft = reSepar.search( line, mEqualSignPrev.end(), mEqualSignAct.start() )
                if mSeparLeft:
                    SeparLeftEnd = mSeparLeft.end()
                    mSeparLeft = reSepar.search( line, mSeparLeft.end(), mEqualSignAct.start() )
                    while mSeparLeft:     # search next
                        SeparLeftEnd = mSeparLeft.end()
                        mSeparLeft = reSepar.search( line, mSeparLeft.end(), mEqualSignAct.start() )
                    LeftStarts.append( SeparLeftEnd )

                mColonLeft = reColonLeft.search( line, mEqualSignPrev.end(), mEqualSignAct.start() )
                if mColonLeft:
                    LeftStarts.append( mColonLeft.end() )
                mBeginOfLine = re.search( '^ *', line )
                LeftStarts.append( mBeginOfLine.end() )
                LeftActStart = max( LeftStarts )

                # Determine RightActEnd,
                # the smaller of mEqualSignNext, mSeparRight, endofline
                RightEnds = []
                mEqualSignNext = reEqualSign.search( line, mEqualSignAct.end() )
                if mEqualSignNext:
                    RightEnds.append( mEqualSignNext.start() )
                mSeparRight = reSepar.search( line, mEqualSignAct.end() )
                if mSeparRight:
                    RightEnds.append( mSeparRight.start() )
                mEndOfLine = re.search( ' *$', line )
                RightEnds.append( mEndOfLine.start() )
                RightActEnd = min( RightEnds )

                rangolibre   = line[ RightPrevEnd          : LeftActStart ]
                rangoLeft    = line[ LeftActStart          : mEqualSignAct.start() ]
                rangocentro  = line[ mEqualSignAct.start() : mEqualSignAct.end() ]
                rangoRight   = line[ mEqualSignAct.end()   : RightActEnd ]

                tipoLeft, valorLeft = TypeAndValueOf( rangoLeft )
                tipoRight, valorRight = TypeAndValueOf( rangoRight )

                if tipoLeft != 'v': # there is something to the left

                    # perform operations

                    if tipoLeft in 'eaif' and tipoRight in 'vif':# evaluate expression
                        try:
                            resultado = str( evaluate( valorLeft,
                                        variables=variables, functions=functions ) )
                            self.writeResult( i, lines, mEqualSignAct.end(), RightActEnd, resultado )
                        except:
                            print 'eval error:', tipoLeft, valorLeft, tipoRight, valorRight
                    elif tipoLeft == 'n' and tipoRight in 'ifav':
                        if valorLeft not in functions:     # variable on the left
                            if tipoRight != 'v':    # assign to variable
                                try:
                                    variables[ valorLeft ] = str( evaluate( str( valorRight),
                                                            variables=variables, functions=functions ) )

                                except:
                                    print 'exec error:', tipoLeft, valorLeft, tipoRight, valorRight
                                    raise
                            else:                   # evaluate a variable
                                if valorLeft in variables:
                                        resultado = variables[ valorLeft ]
                                        resultado = AddCommas( resultado )
                                        self.writeResult( i, lines, mEqualSignAct.end(), RightActEnd, resultado )

                        else:                                  # function on the left: evaluate
                            if valorLeft not in functions[ valorLeft ]:
                                try:                # standard formula
                                    resultado = str( evaluate( valorLeft,
                                                variables=variables, functions=functions ) )
                                    self.writeResult( i, lines, mEqualSignAct.end(), RightActEnd, resultado )
                                except:
                                    print 'eval error:', tipoLeft, valorLeft, tipoRight, valorRight
                            else:                   # recurrence relation
                                if valorLeft not in variables:            # initial value
                                  if valorRight != '':
                                    variables[ valorLeft ] = str( evaluate( str( valorRight ),
                                                            variables=variables, functions=functions ) )
                                else:                                         # iteration
                                    resultado = str( evaluate( functions[ valorLeft ],
                                                    variables=variables, functions=functions ) )
                                    self.writeResult( i, lines, mEqualSignAct.end(), RightActEnd, resultado )
                                    variables[ valorLeft ] = resultado

                    elif tipoLeft == 'n' and tipoRight in 'e': # define a function
                            functions[ valorLeft ] = str(valorRight)

                    elif tipoLeft == 'n' and tipoRight in 'n': # define an alias
                            functions[ valorLeft ] = str(valorRight)



                    RightPrevStart = mEqualSignAct.end()
                    RightPrevEnd = RightActEnd

                # get line
                line = self.readLine( i, lines )

                if mEqualSignNext:
                    mEqualSignNext = reEqualSign.search( line, mEqualSignAct.end() )
                mEqualSignPrev = mEqualSignAct
                mEqualSignAct  = mEqualSignNext


class ParserTk(Parser):
    ''

    def parse( self, textWidget ):
        ''
        for i in range( self.countLines( textWidget ) ):
            self.parseLine( i, textWidget, variables=self.variables, functions=self.functions )

    def countLines( self, textWidget ):
        ''
        return int(textWidget.index( 'end' ).split('.')[0])

    def readLine( self, i, textWidget ):
        ''
        return textWidget.get( str(i) + '.0', str(i) + '.end'   )

    def writeResult( self, i, textWidget, start, end, text ):
        'Write text in line i of lines from start to end offset.'
        textWidget.delete( str(i) + '.' + str(start), str(i) + '.' + str(end) )
        textWidget.insert( str(i) + '.' + str(start), text )

class ParserGTK(Parser):
    ''

    def parse( self, textBuffer ):
        ''
        for i in range( self.countLines( textBuffer ) ):
            self.parseLine( i, textBuffer, variables=self.variables, functions=self.functions )

    def countLines( self, textBuffer ):
        ''
        return textBuffer.get_line_count()

    def readLine( self, i, textBuffer ):
        ''
        iter_start = textBuffer.get_iter_at_line( i )
        if iter_start.ends_line():
            return ''
        else:
            iter_end = textBuffer.get_iter_at_line( i )
            iter_end.forward_to_line_end()
            return textBuffer.get_text( iter_start, iter_end )

    def writeResult( self, i, textBuffer, start, end, text ):
        'Write text in line i of lines from start to end offset.'
        # Delete
        if end > start:
            # handle start at end of line or beyond
            iter_line = textBuffer.get_iter_at_line( i )
            nchars = iter_line.get_chars_in_line()
            if start > nchars-1:
                start = nchars-1
            iter_start = textBuffer.get_iter_at_line_offset( i, start )
            iter_end = textBuffer.get_iter_at_line_offset( i, end )
            textBuffer.delete( iter_start, iter_end )

        # Insert
        iter_start = textBuffer.get_iter_at_line_offset( i, start )
        textBuffer.insert( iter_start, text )

class ParserWx(Parser):
    ''

    def parse( self, TextControl ):
        ''
        for i in range( self.countLines( TextControl ) ):
            self.parseLine( i, TextControl, variables=self.variables, functions=self.functions )

    def countLines( self, TextControl ):
        ''
        return TextControl.GetNumberOfLines()

    def readLine( self, i, TextControl ):
        ''
        return TextControl.GetLineText(i)

    def writeResult( self, i, TextControl, start, end, text ):
        'Write text in line i of lines from start to end offset.'

        # Convert line, column to offset
        startOffset = TextControl.XYToPosition( start, i)
        endOffset = TextControl.XYToPosition( end, i)
        TextControl.Replace( startOffset, endOffset, text )

def feed( text ):
    'Feed text to the parser.  It is processed line by line.'

    # Create instance of parser
    parser = Parser()

    # Parse the text
    return parser.parse( text )


def AddCommas( s ):
    ''''Return s with thousands separators.

    Handles sign, decimals and thousands
    separator.
    '''

    s = str( s )
    s = s.replace( ',', '')         #remove commas
    if s[0] in '-+':                #remove sign
            sign = s[0]
            s = s[1:]
    else:
            sign = ''
    if s[-1] == 'L': s = s[:-1]     #remove L suffix
    pos = s.find( '.')
    if pos < 0: pos = len(s)
    while pos > 3:
            pos = pos - 3
            s = s[:pos] + ',' + s[pos:]
    s = sign + s                    #restore sign
    return s

if __name__ == '__main__':
    import sys
    if len( sys.argv ) >= 2:
        if sys.argv[1] in [ '-h', '--help' ]:
            print __doc__
        elif sys.argv[1] == '-f':
            filename = sys.argv[2]
            text = open( filename ).read()
            print feed( text )
        else:
            text =  ' '.join( sys.argv[ 1: ] )
            if '=' in text:
                print feed( text )
            else:
                print evaluate( text )
    else:
        text = sys.stdin.read()
        lines = text.splitlines()
        if '=' in text or len(lines) > 1:
            print feed( text )
        else:
            print evaluate( lines[0] )

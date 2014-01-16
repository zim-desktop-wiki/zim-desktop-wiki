Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.4
Creation-Date: 2010-08-31T22:25:42.585662

====== Inline Calculator ======

This plugin allows you to evaluate simple mathematical expressions in zim.

**Dependencies:** This plugin has no additional dependencies.

**See also:** the [[Arithmetic|Arithmetic plugin]] which does something similar

===== Examples =====
Simple expressions can be evaluated on a single line:

	3 + 3 = 	

When you press "Tools" -> "Evaluate Math" the result of the expression is automatically added behind the "=" sign. Note that the cursor needs to be behind the expression you want to evaluate.
If there is text on the same line before the expression it should end with an ":". For example:

	Fuel: 30 + 27.5 =

Other words in front of the formula can result in errors.

Apart from single line expressions you can also do multi-line summations and subtractions.  The syntax for this is like this:

	7
	3
	5
	--- +

In this case the cursor needs to be below the summation when you trigger the evaluation.

===== Functions =====
The following functions are available:

From standard python functions
'''
abs
ord
chr
hex
oct
int
'''

From math and cmath modules in standard python library:
'''
atan2
fmod
frexp
hypot
ldexp
modf
acos
asin
atan
cos
cosh
sin
sinh
tan
tanh
exp
log10
sqrt
'''

Other:
'''
degrees
radians
log
real
imag
sign
log2
gcd
lcm
phase
conj
round
floor
ceil
'''

Synonyms:
'''
mag - same as abs()
angle - same as phase()

'''
''Constants:''
'''
e
pi
j
'''

# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.plugins import PluginManager


@tests.slowTest
class TestPrintToBrowser(tests.TestCase):

	def runTest(self):
		'Test InlineCalculator plugin'
		pluginklass = PluginManager.get_plugin_class('inlinecalculator')
		plugin = pluginklass()

		for text, wanted in (
			('3 + 4 =', '3 + 4 = 7'),
			('3 + 4 = 1', '3 + 4 = 7'),
			('3 + 4 = 1 ', '3 + 4 = 7 '),
			('10 / 3 =', '10 / 3 = 3.33333333333'), # divide integers to float !
			('milage: 3 + 4 =', 'milage: 3 + 4 = 7'),
			('3 + 4 = 7 + 0.5 =  ', '3 + 4 = 7 + 0.5 = 7.5'),
			('''\
5.5
 4.3
3.1
--- +
''',

			'''\
5.5
 4.3
3.1
--- +
12.9
'''			),
		):
			result = plugin.process_text(text)
			self.assertEqual(result, wanted)

		# Tests from clac.py self test
		for test in '''\
1+2 == 3
sqrt(-1) == j
-2*asin(-1) == pi
abs(sin(pi)) < 1e-9
abs(1-cos(0)) < 1e-9
round( 3.1 + -4.8j) == (3-5j)
ceil( 3.1 + -4.8j) == (4-4j)
abs( 3-4j) == 5
degrees(pi) == 180
radians(180) == pi
abs( exp(j*pi) + 1 ) < 1e-9
# pow(1.2,3.4) == 1.2**3.4
ldexp(1.2,3) == 1.2 * 2 ** 3
modf(1.2)[1] == 1
log(81,3) == 4
gcd(6,8) == 2
lcm(6,8) == 24
angle( exp( j*pi ) ) == pi
# log(-1)**2 == -1*pow(pi,2)
round( degrees(phase( e**(2j)))) == 115
# sum( [ round(42 * exp(j*2*x*pi/4)) for x in range(4)] ) == 0
oct(8) == '010'
0x42-042-42 == -10
# 1k == 1024
# 1m == 2**20
# 1g == 2**30
2**10-1 == 1023
# 2**1k == 2**1024
'''.splitlines():
			if test.startswith('#'):
				continue
			#~ print 'TESTING:', test
			self.assertTrue(plugin.safe_eval(test))

		self.assertRaises(Exception, plugin.process_text, 'open("/etc/passwd")') # global
		self.assertRaises(Exception, plugin.process_text, 'self') # local


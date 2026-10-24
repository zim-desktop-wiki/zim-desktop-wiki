"""Tests for the temporary Windows emoji fallback workaround."""

import os
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch


class TestWindowsFontconfig(unittest.TestCase):

	def setUp(self):
		self.scriptfile = os.path.abspath('zim.py')
		self.init_environment = runpy.run_path(self.scriptfile)['init_environment']
		folder = tempfile.TemporaryDirectory(prefix='zim-fontconfig-')
		self.addCleanup(folder.cleanup)
		self.installdir = folder.name
		self.config_file = self.write_file('windows/src/fontconfig/fonts.conf', '<fontconfig />')
		environment = patch.dict(os.environ, {'XDG_DATA_DIRS': 'TEST'}, clear=True)
		environment.start()
		self.addCleanup(environment.stop)

	def write_file(self, relative_path, text):
		path = os.path.join(self.installdir, *relative_path.split('/'))
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, 'w', encoding='utf-8') as stream:
			stream.write(text)
		return path

	def init_for_platform(self, platform):
		with patch.object(sys, 'platform', platform):
			self.init_environment(self.installdir)

	def testWindowsSource(self):
		self.init_for_platform('win32')
		self.assertEqual(os.environ['PANGOCAIRO_BACKEND'], 'fc')
		self.assertEqual(os.environ['FONTCONFIG_FILE'], self.config_file)

	def testPackagedLayouts(self):
		os.remove(self.config_file)
		for relative_path in ('config/fontconfig/fonts.conf', '_internal/config/fontconfig/fonts.conf'):
			with self.subTest(path=relative_path):
				config_file = self.write_file(relative_path, '<fontconfig />')
				with patch.dict(os.environ, {'XDG_DATA_DIRS': 'TEST'}, clear=True):
					self.init_for_platform('win32')
					self.assertEqual(os.environ['PANGOCAIRO_BACKEND'], 'fc')
					self.assertEqual(os.environ['FONTCONFIG_FILE'], config_file)
				os.remove(config_file)

	def testNonWindows(self):
		for platform in ('linux', 'darwin'):
			with self.subTest(platform=platform):
				self.init_for_platform(platform)
				self.assertNotIn('PANGOCAIRO_BACKEND', os.environ)
				self.assertNotIn('FONTCONFIG_FILE', os.environ)

	def testExplicitBackend(self):
		for backend in ('win32', ''):
			with self.subTest(backend=backend):
				os.environ['PANGOCAIRO_BACKEND'] = backend
				self.init_for_platform('win32')
				self.assertEqual(os.environ['PANGOCAIRO_BACKEND'], backend)
				self.assertNotIn('FONTCONFIG_FILE', os.environ)

	def testExplicitFontconfig(self):
		for key in ('FONTCONFIG_FILE', 'FONTCONFIG_PATH'):
			for value in ('custom-fontconfig', ''):
				with self.subTest(key=key, value=value):
					with patch.dict(os.environ, {key: value}, clear=True):
						self.init_for_platform('win32')
						self.assertEqual(os.environ['PANGOCAIRO_BACKEND'], 'fc')
						self.assertEqual(os.environ[key], value)
						if key == 'FONTCONFIG_PATH':
							self.assertNotIn('FONTCONFIG_FILE', os.environ)

	def testExplicitFCBackend(self):
		os.environ['PANGOCAIRO_BACKEND'] = 'fc'
		self.init_for_platform('win32')
		self.assertEqual(os.environ['FONTCONFIG_FILE'], self.config_file)

	def testEnvironINI(self):
		self.write_file('environ.ini', '[Environment]\nFONTCONFIG_FILE=./custom/fonts.conf\n')
		self.init_for_platform('win32')
		self.assertEqual(os.environ['PANGOCAIRO_BACKEND'], 'fc')
		self.assertEqual(os.environ['FONTCONFIG_FILE'], os.path.join(self.installdir, 'custom', 'fonts.conf'))

	def testEnvironINIDisablesWorkaround(self):
		self.write_file('environ.ini', '[Environment]\nPANGOCAIRO_BACKEND=win32\n')
		self.init_for_platform('win32')
		self.assertEqual(os.environ['PANGOCAIRO_BACKEND'], 'win32')
		self.assertNotIn('FONTCONFIG_FILE', os.environ)

	def testMissingConfiguration(self):
		os.remove(self.config_file)
		self.init_for_platform('win32')
		self.assertNotIn('PANGOCAIRO_BACKEND', os.environ)
		self.assertNotIn('FONTCONFIG_FILE', os.environ)

	def testPathsIndependentOfWorkingDirectory(self):
		cwd = os.getcwd()
		try:
			os.chdir(self.installdir)
			self.init_for_platform('win32')
		finally:
			os.chdir(cwd)
		self.assertEqual(os.environ['FONTCONFIG_FILE'], self.config_file)

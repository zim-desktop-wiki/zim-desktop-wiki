# -*- coding: utf-8 -*-

# Copyright 2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import gtk

from zim.actions import *


class TestPrimaryKeyBinding(tests.TestCase):

	def runTest(self):
		for accel in ( # Ctrl-A or Command-A
			"<Control>a",
			"<Meta>a",
			"<Primary>A",
			"<primary>A",
			"<PRIMARY>a"
		):
			#~ print ">>", accel, gtk_accelerator_preparse(accel)
			keyval, mod = gtk.accelerator_parse(
				gtk_accelerator_preparse(accel)
			)
			self.assertEqual(keyval, 97)
			self.assertIn(mod, (gtk.gdk.CONTROL_MASK, gtk.gdk.META_MASK))

		for accel in (
			"<Shift>A", "<Control>A", "<Alt>A",
			'', None,
		):
			self.assertEqual(gtk_accelerator_preparse(accel), accel)


class TestAction(tests.TestCase):

	def runTest(self):
		output = []

		class TestClass(object):

			@action('Do Action', accelerator='<Control>A')
			def test_action(self):
				return output.append('OK')

		self.assertIsInstance(TestClass.test_action, Action)

		obj = TestClass()
		obj.test_action()
		self.assertEqual(output, ['OK'])

		gtk_group = get_gtk_actiongroup(obj)
		gtk_action = gtk_group.get_action('test_action')
		self.assertIsInstance(gtk_action, gtk.Action)
		self.assertEqual(gtk_group.list_actions(), [gtk_action])

		gtk_action.activate()
		self.assertEqual(output, ['OK', 'OK'])


class TestToggleAction(tests.TestCase):

	def runTest(self):
		output = []

		class TestClass(object):

			@toggle_action('Do Action', accelerator='<Control>A')
			def test_action(self, active):
				return output.append(active)

		self.assertIsInstance(TestClass.test_action, ToggleAction)

		obj = TestClass()
		obj.test_action()
		self.assertEqual(output, [True])
		obj.test_action()
		self.assertEqual(output, [True, False])
		obj.test_action(False)
		self.assertEqual(output, [True, False]) # no change
		obj.test_action(True)
		self.assertEqual(output, [True, False, True])

		gtk_group = get_gtk_actiongroup(obj)
		gtk_action = gtk_group.get_action('test_action')
		self.assertIsInstance(gtk_action, gtk.ToggleAction)
		self.assertEqual(gtk_group.list_actions(), [gtk_action])

		self.assertEqual(gtk_action.get_active(), True) # correct init state
		gtk_action.activate()
		self.assertEqual(output, [True, False, True, False])

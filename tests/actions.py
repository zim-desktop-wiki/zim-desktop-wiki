# -*- coding: utf-8 -*-

# Copyright 2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import gtk

from zim.actions import *


class TestPrimaryKeyBinding(tests.TestCase):

    def runTest(self):
        for accel in (  # Ctrl-A or Command-A
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
                output.append('OK')
                return 'FOO'

        self.assertIsInstance(TestClass.test_action, Action)

        obj = TestClass()
        re = obj.test_action()
        self.assertEqual(output, ['OK'])
        self.assertIsNone(re)  # do not allow return value for actions!

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
                output.append(active)
                return 'FOO'

        self.assertIsInstance(TestClass.test_action, ToggleAction)

        obj = TestClass()
        re = obj.test_action()
        self.assertEqual(output, [True])
        self.assertIsNone(re)  # do not allow return value for actions!

        obj.test_action()
        self.assertEqual(output, [True, False])
        obj.test_action(False)
        self.assertEqual(output, [True, False])  # no change
        obj.test_action(True)
        self.assertEqual(output, [True, False, True])

        gtk_group = get_gtk_actiongroup(obj)
        gtk_action = gtk_group.get_action('test_action')
        self.assertIsInstance(gtk_action, gtk.ToggleAction)
        self.assertEqual(gtk_group.list_actions(), [gtk_action])

        self.assertEqual(gtk_action.get_active(), True)  # correct init state
        gtk_action.activate()
        self.assertEqual(output, [True, False, True, False])


class TestRadioAction(tests.TestCase):

    def runTest(self):
        output = []

        class TestClass(object):

            @radio_action(
                    radio_option('AAA', 'Do A'),
                    radio_option('BBB', 'Do B')
            )
            def test_action(self, key):
                output.append(key)
                return 'FOO'

        self.assertIsInstance(TestClass.test_action, RadioAction)

        obj = TestClass()
        re = obj.test_action('AAA')
        self.assertIsNone(re)  # do not allow return value for actions!

        obj.test_action('BBB')
        self.assertEqual(output, ['AAA', 'BBB'])

        self.assertRaises(ValueError, obj.test_action, 'CCC')

        gtk_group = get_gtk_actiongroup(obj)
        self.assertEqual(
                sorted(a.get_name() for a in gtk_group.list_actions()),
                ['test_action_AAA', 'test_action_BBB']
        )

        gtk_action = gtk_group.get_action('test_action_AAA')
        self.assertIsInstance(gtk_action, gtk.RadioAction)
        gtk_action.activate()
        self.assertEqual(output, ['AAA', 'BBB', 'AAA'])

#!/usr/bin/python3

"""
    This module is meant to be run as script to clean up all of Zim's python
    code. It mostly works by applying fixes provided by autopep8 to make code
    comply to the PEP8 standard, https://www.python.org/dev/peps/pep-0008/ .

    Copyright: Christian Stadelmann, 2017
"""


import os
import subprocess
import tempfile


class CleanupTask(object):
    """
        An abstract base class for cleanup tasks.
    """

    def __init__(self, name, description):
        self._name = name
        self._description = description

    def cleanup_func(self):
        """
            Child classes should implement their cleanup code here.
        """
        raise NotImplementedError()

    def commit_to_git(self):
        """
            A convenience function to commit any changes to git
        """
        git_cmd = ["git", "diff", "--name-only"]
        complproc = subprocess.run(git_cmd, stdout=subprocess.PIPE, check=True)
        if not complproc.stdout or complproc.stdout.isspace():
            print(("Not commiting anything because nothing changed in cleanup "
                  "task %s" % self._name))
            return

        print(("Commiting changes for cleanup task %s" % self._name))

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmpfile:
            tmpfile.write(self._name)
            tmpfile.write("\n\n")
            tmpfile.write(self._description)

        git_cmd = ["git", "commit", "-a", "-F", tmpfile.name]
        subprocess.run(git_cmd, check=True)

        os.remove(tmpfile.name)


class UnifyLineEndings(CleanupTask):

    def __init__(self):
        CleanupTask.__init__(self,
                             "Fix line separation characters",
                             "Replace \\r\\n by \\n everywhere.")

    def cleanup_func(self):
        for root, dirs, files in os.walk('.'):
            for name in files:
                if name[-3:] == '.py':
                    filename = os.path.join(root, name)
                    UnifyLineEndings.__cleanup_file(filename)

    @staticmethod
    def __cleanup_file(filename):
        data = None
        dirty = False
        with open(filename, mode='r', newline='') as file:
            data = file.read()
            if '\r\n' in data:
                data = data.replace('\r\n', '\n')
                dirty = True
            if '\r' in data:
                data = data.replace('\r', '\n')
                dirty = True
        if dirty:
            new_filename = filename + '.new'
            with open(new_filename, mode='w', newline='\n') as new_file:
                new_file.write(data)
            os.replace(new_filename, filename)


class Autopep8Task(CleanupTask):
    """
        An abstract class for running autopep8 to clean up code.
    """

    def __init__(self, name, pep8_classes):
        self.__cmd = ["autopep8", "--jobs", "4", "--aggressive",
                      "--in-place", "--recursive", "--select", pep8_classes,
                      "."]
        name = "Autopep8: %s" % name
        description = \
            "Run the '%s' fixer(s) from autopep8 over Zim source: \n\t`%s`" % (
                name, " ".join(self.__cmd)
            )
        CleanupTask.__init__(self, name, description)

    def cleanup_func(self):
        print((self._description))
        subprocess.run(self.__cmd, check=True)


def _get_tests():
    unify_line_endings = UnifyLineEndings()
    autopep8_indentation_tabs = Autopep8Task(
        "Indentation contains mixed spaces and tabs", "E101")
    autopep8_statements_on_separate_lines = Autopep8Task(
        "Statements on separate lines", "E701,E702,E703")
    autopep8_more_statements = Autopep8Task(
        "More Statements", "E7")
    autopep8_deprecations = Autopep8Task(
        "Deprecation warning", "W6")
    autopep8_blackslash = Autopep8Task(
        "The backslash is redundant between brackets", "E502")
    autopep8_imports = Autopep8Task(
        "Imports", "E4")
    autopep8_whitespace_in_code = Autopep8Task(
        "Whitespace in code", "E20,E21,E22,E23,E24,E27")
    autopep8_whitespace_in_comments = Autopep8Task(
        "Whitespace in comments", "E26")
    autopep8_blank_lines = Autopep8Task(
        "Blank line", "E3,W3")
    autopep8_indentation_in_comments = Autopep8Task(
        "Indentation in comments", "E11")
    autopep8_indentation_in_code = Autopep8Task(
        "Indentation in code", "E12,W1")

    # please note: the order is important here!
    return [unify_line_endings,
            # autopep8_indentation_tabs,
            autopep8_statements_on_separate_lines,
            autopep8_more_statements,
            autopep8_deprecations,
            autopep8_blackslash,
            autopep8_imports,
            autopep8_whitespace_in_code,
            #autopep8_whitespace_in_comments,
            #autopep8_blank_lines,
            #autopep8_indentation_in_comments,
            #autopep8_indentation_in_code,
           ]


def main():
    subprocess.run(['make', 'clean'])

    cleaners = _get_tests()

    for cleaner in cleaners:
        cleaner.cleanup_func()
        cleaner.commit_to_git()
    exit(0)

if __name__ == '__main__':
    main()

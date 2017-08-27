# -*- coding: iso-8859-1 -*-
# Written by Martin v. Lwis <loewis@informatik.hu-berlin.de>
# Plural forms support added by alexander smishlajev <alex@tycobka.lv>
"""
Generate binary message catalog from textual translation description.

This program converts a textual Uniforum-style message catalog (.po file) into
a binary GNU catalog (.mo file).  This is essentially the same function as the
GNU msgfmt program, however, it is a simpler implementation.

Usage: msgfmt.py [OPTIONS] filename.po

Options:
    -o file
    --output-file=file
        Specify the output file to write to.  If omitted, output will go to a
        file named filename.mo (based off the input file name).

    -h
    --help
        Print this message and exit.

    -V
    --version
        Display version information and exit.
"""

import sys
import os
import getopt
import struct
import array

__version__ = "1.1"

MESSAGES = {}


def usage(ecode, msg=''):
    """
    Print usage and msg and exit with given code.
    """
    print >> sys.stderr, __doc__
    if msg:
        print >> sys.stderr, msg
    sys.exit(ecode)


def add(msgid, transtr, fuzzy):
    """
    Add a non-fuzzy translation to the dictionary.
    """
    global MESSAGES
    if not fuzzy and transtr and not transtr.startswith('\0'):
        MESSAGES[msgid] = transtr


def generate():
    """
    Return the generated output.
    """
    global MESSAGES
    keys = sorted(MESSAGES.keys())
    # the keys are sorted in the .mo file
    offsets = []
    ids = strs = ''
    for _id in keys:
        # For each string, we need size and file offset.  Each string is NUL
        # terminated; the NUL does not count into the size.
        offsets.append((len(ids), len(_id), len(strs), len(MESSAGES[_id])))
        ids += _id + '\0'
        strs += MESSAGES[_id] + '\0'
    # The header is 7 32-bit unsigned integers.  We don't use hash tables, so
    # the keys start right after the index tables.
    # translated string.
    keystart = 7 * 4 + 16 * len(keys)
    # and the values start after the keys
    valuestart = keystart + len(ids)
    koffsets = []
    voffsets = []
    # The string table first has the list of keys, then the list of values.
    # Each entry has first the size of the string, then the file offset.
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]
    offsets = koffsets + voffsets
    output = struct.pack("Iiiiiii",
                         0x950412de,       # Magic
                         0,                 # Version
                         len(keys),         # # of entries
                         7 * 4,               # start of key index
                         7 * 4 + len(keys) * 8,   # start of value index
                         0, 0)              # size and offset of hash table
    output += array.array("i", offsets).tostring()
    output += ids
    output += strs
    return output


def make(filename, outfile):
    ID = 1
    STR = 2
    global MESSAGES
    MESSAGES = {}

    # Compute .mo name from .po name and arguments
    if filename.endswith('.po'):
        infile = filename
    else:
        infile = filename + '.po'
    if outfile is None:
        outfile = os.path.splitext(infile)[0] + '.mo'

    try:
        lines = open(infile).readlines()
    except IOError as msg:
        print >> sys.stderr, msg
        sys.exit(1)

    section = None
    fuzzy = 0

    # Parse the catalog
    msgid = msgstr = ''
    lno = 0
    for l in lines:
        lno += 1
        # If we get a comment line after a msgstr, this is a new entry
        if l[0] == '#' and section == STR:
            add(msgid, msgstr, fuzzy)
            section = None
            fuzzy = 0
        # Record a fuzzy mark
        if l[:2] == '#,' and (l.find('fuzzy') >= 0):
            fuzzy = 1
        # Skip comments
        if l[0] == '#':
            continue
        # Start of msgid_plural section, separate from singular form with \0
        if l.startswith('msgid_plural'):
            msgid += '\0'
            l = l[12:]
        # Now we are in a msgid section, output previous section
        elif l.startswith('msgid'):
            if section == STR:
                add(msgid, msgstr, fuzzy)
            section = ID
            l = l[5:]
            msgid = msgstr = ''
        # Now we are in a msgstr section
        elif l.startswith('msgstr'):
            section = STR
            l = l[6:]
            # Check for plural forms
            if l.startswith('['):
                # Separate plural forms with \0
                if not l.startswith('[0]'):
                    msgstr += '\0'
                # Ignore the index - must come in sequence
                l = l[l.index(']') + 1:]
        # Skip empty lines
        l = l.strip()
        if not l:
            continue
        # XXX: Does this always follow Python escape semantics?
        l = eval(l)
        if section == ID:
            msgid += l
        elif section == STR:
            msgstr += l
        else:
            print >> sys.stderr, 'Syntax error on %s:%d' % (infile, lno), \
                'before:'
            print >> sys.stderr, l
            sys.exit(1)
    # Add last entry
    if section == STR:
        add(msgid, msgstr, fuzzy)

    # Compute output
    output = generate()

    try:
        open(outfile, "wb").write(output)
    except IOError as msg:
        print >> sys.stderr, msg


def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hVo:',
                                   ['help', 'version', 'output-file='])
    except getopt.error as msg:
        usage(1, msg)

    outfile = None
    # parse options
    for opt, arg in opts:
        if opt in ('-h', '--help'):
            usage(0)
        elif opt in ('-V', '--version'):
            print >> sys.stderr, "msgfmt.py", __version__
            sys.exit(0)
        elif opt in ('-o', '--output-file'):
            outfile = arg
    # do it
    if not args:
        print >> sys.stderr, 'No input file given'
        print >> sys.stderr, "Try `msgfmt --help' for more information."
        return

    for filename in args:
        make(filename, outfile)


if __name__ == '__main__':
    main()

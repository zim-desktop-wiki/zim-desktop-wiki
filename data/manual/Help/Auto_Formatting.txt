Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.4
Creation-Date: Unknown

====== Auto Formatting ======

Auto-formatting means that zim parses text while you type. Be aware that the syntax for auto-formatting isn't the same as the [[Wiki Syntax|wiki syntax]] for the source formatting (the wiki format as it is saved to the files). If you typed in source syntax and you want to have it rendered you should reload the page (press ^R).

Enable "**Reformat wiki format on the fly**" in the preferences to enable this feature.

If auto-formatting does something you didn't intend you can reverse it by pressing ''<ctrl>Z''.

===== Headings =====
Typing:

'''
== Heading 1 <ENTER>
'''

gives you a heading 1 and typing:

'''
=== Heading 2<ENTER>
'''

gives you a heading 2. But in the corresponding text file these headings are marked as follows:

'''
====== Heading 1 ======
===== Heading 2 =====
'''


===== Links =====
When you type an internet URL like http://perl.org, it will automatically be identified as a link.

There are several other link types that can optionally be auto-formatted. See the [[Preferences]] to control these and see [[Links]] for more information on the link syntax

* Words in "CamelCase" can be considered a link automatically. Once again this auto-formatting is done by the editor, your source format does not have to support CamelCase.
* Wiki page names like ``Page:SubPage``, ``+SubPage``, ``:Page`` or ``Page#heading`` can be auto-formatted
* Identifiers like ``#heading`` can be auto-formatted
* Interwiki links like ``wp?Topic`` can be auto-formatted
* File paths like ``./screenshot.png`` can be auto-formatted

If auto-formatting is disabled, these links can still be created by the "Insert Link" dialog.

When auto-formatting page links the link must have at least 2 letters in the first part of the link to avoid linking strings like e.g. "10:20PM". Also see [[Pages]] for more information on page names.


===== Bullets and Checkboxes =====
Another example of auto-formatting is that "* " at the beginning of a line gets converted to a bullet automatically. Typing either "[] ", "[*] ", "[x] ", "[>] " or "() ", "(*) ", "(x) ", "(>) " will give your different kinds of [[Check Boxes]].

===== Horizontal line =====
Typing five dashes:

''-----''

gives you a horizontal line:

--------------------

===== Sub- and superscript =====

For subscript ''word_{word}'' will be auto-formatted, e.g. typing ''H_{2}O''. This
only works if there are no spaces in the sequence.

For superscript ''word^{word}'' or ''word^word'' will be auto-formatted. These
only work if there are no spaces in the sequences.

===== Anchor objects =====

Typing ``##name`` will insert an special object that can be linked to as an identifier. If enabled, typing ``#name`` will insert a link to the same object.


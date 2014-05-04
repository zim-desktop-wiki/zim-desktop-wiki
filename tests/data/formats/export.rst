Head 1
======
Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do
eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim
ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut
aliquip ex ea commodo consequat. Duis aute irure dolor in
reprehenderit in voluptate velit esse cillum dolore eu fugiat
nulla pariatur.  Excepteur sint occaecat cupidatat non proident,
sunt in culpa qui officia deserunt mollit anim id est laborum.

	Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do
	eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim
	ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut
	aliquip ex ea commodo consequat. Duis aute irure dolor in
	reprehenderit in voluptate velit esse cillum dolore eu fugiat
	nulla pariatur.  Excepteur sint occaecat cupidatat non proident,
	sunt in culpa qui officia deserunt mollit anim id est laborum.

head 2
------

**bold**, *italic* and underline and ``verbatim``
and also strike through

This is not formatted: *bold*, /italic/ / * *^%#@#$#!@)_!)_ & <> ""

Some sub- and superscript like x\ :sup:`2`\  and H\ :sub:`2`\ O

And some empty space here:



head 3
^^^^^^
`foo <foo>`_  links to page in the current namespace or parents
`:foo <:foo>`_ links to page in the root namespace
`+foo <+foo>`_ links to page in a subnamespace
`bar <foo>`_ links to "foo" but display "bar"

`:foo:bar <:foo:bar>`_ `./file.png <./file.png>`_ `file:///etc/passwd <file:///etc/passwd>`_
`Foo <Foo>`_`Bar <Bar>`_

`mailto:foo@bar.org <mailto:foo@bar.org>`_
`wp?Test <interwiki:wp?Test>`_

External links like `http://nongnu.org <http://nongnu.org>`_ and `foo@bar.org <mailto:foo@bar.org>`_ are also supported

[not:a:link]


.. image:: ./foobar.png


.. image:: ./foobar.png
   :height: 50


.. image:: ../my-image.png
   :alt: Foo Bar
   :width: 600


.. image:: my-image.png
   :href: Foo


.. image:: ../my-image.png
   :alt: Foo Bar
   :href: :foo:bar
   :width: 600



.. image:: ./equation001.png
   :type: equation

 This equation has a source .tex file
.. image:: ./equation002.png
   :type: equation

 for this one it is missing

{./Not/an/image.png}

Tags: @foo @bar


head 4
""""""

- item 1
- item 2
- item 3
	- item a
	- item b
- item 4


Indented list:
	- item 1
	- item 2
	- item 3
		- item a
		- item b
	- item 4


TODO list:
- ☐ foo
- ☑ bar
	- ☑ sub item 1
		- Some normal bullet
	- ☑ sub item 2
- ☒ baz


A numbered list:
1. foo
2. bar
	a. sub list
	b. here
3. hmmm


Start with number other that 1/a/A

C. foo
D. bar
	3. sub item start with 3
E. baz

head 5
""""""
*some verbatim blocks*:

::

	Sing, O goddess, the rage of
	Achilles son of Peleus, that
	brought countless ills upon
	the Achaeans.

::

	Sing, O goddess, the rage of
	Achilles son of Peleus, that
	brought countless ills upon
	the Achaeans.

::

	def foo(self, bar, baz):
		'''Some doc string here
		@param bar: value for bar
		@param baz: value for baz
		@returns: foo
		'''
		returen "foo" + bar % baz

Internationalization
--------------------

中文
^^
This section has a chinese heading

Lines below are in right to left script:

חדו"א
מד"ר
מכניקת מוצקים 2
A line in English, should be left aligned.
דינמיקה

aaa


Some Objects
------------

::

	def dump():
		for i in range(1, 5):
			print i


::

	Sing, O goddess, the rage of
	Achilles son of Peleus, that
	brought countless ills upon
	the Achaeans.


====
This is not a header

That's all ...

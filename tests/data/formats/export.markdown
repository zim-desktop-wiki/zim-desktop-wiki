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

**bold**, *italic* and __underline__ and ``verbatim``
and also ~~strike through~~

This is not formatted: *bold*, /italic/ / * *^%#@#$#!@)_!)_ & <> ""

Some sub- and superscript like x^2^ and H~2~O

And some empty space here:



### head 3
[foo](foo)  links to page in the current namespace or parents
[:foo](:foo) links to page in the root namespace
[+foo](+foo) links to page in a subnamespace
[bar](foo) links to "foo" but display "bar"

[:foo:bar](:foo:bar) [./file.png](./file.png) <file:///etc/passwd>

<mailto:foo@bar.org>
[wp?Test](interwiki:wp?Test)

External links like <http://nongnu.org> and [foo@bar.org](mailto:foo@bar.org) are also supported

[not:a:link]


![](./foobar.png)
![](./foobar.png)
![Foo Bar](../my-image.png)
![](my-image.png)
![Foo Bar](../my-image.png)

![](./equation001.png) This equation has a source .tex file
![](./equation002.png) for this one it is missing

{./Not/an/image.png}

Tags: @foo @bar

Anchors: [id: foo]  [#foo](#foo)  [page#foo](page#foo)


#### head 4 [id: head-4-anchor]


* item 1
* item 2
* item 3
	* item a
	* item b
* item 4



Indented list:

* item 1
* item 2
* item 3
	* item a
	* item b
* item 4



TODO list:

* ☐ foo
* ☑ bar
	* ☑ sub item 1
		* Some normal bullet
	* ☑ sub item 2
* ☒ baz



* ▷ Migrated checkbox
* ◁ Transmigrated checkbox


A numbered list:

1. foo
2. bar
	1. sub list
	2. here
3. hmmm



Start with number other that 1/a/A


3. foo
4. bar
	3. sub item start with 3
5. baz


##### head 5
*some verbatim blocks*:

	Sing, O goddess, the rage of
	Achilles son of Peleus, that
	brought countless ills upon
	the Achaeans.

	Sing, O goddess, the rage of
	Achilles son of Peleus, that
	brought countless ills upon
	the Achaeans.

	def foo(self, bar, baz):
		'''Some doc string here
		@param bar: value for bar
		@param baz: value for baz
		@returns: foo
		'''
		returen "foo" + bar % baz

Internationalization
--------------------

### 中文
This section has a chinese heading

Lines below are in right to left script:

חדו"א
מד"ר
מכניקת מוצקים 2
A line in English, should be left aligned.
דינמיקה

aaa


A horizontal line

*****

And more text


Some Objects
------------

	def dump():
		for i in range(1, 5):
			print i


	Sing, O goddess, the rage of
	Achilles son of Peleus, that
	brought countless ills upon
	the Achaeans.

A table
-------

|        H1        |                        H2 h2 | H3                   |
|:----------------:|-----------------------------:|:---------------------|
|    Column A1     |                    Column A2 | a                    |
| a very long cell |                **bold text** | b                    |
|    hyperlinks    | [wp?wiki](interwiki:wp?wiki) | [Xorg](http://x.org) |

Multiformatting **bold**
------------------------

normal **bold** normal2
normal ~~strike **nested bold** strike2~~ normal2
normal ~~strike **nested bold** strike2~~ *italic [link](https://example.org)* normal2
normal ~~strike  **nested bold** middle of the text *italic [link](https://example.org)* yet another text **another bold *yet another italic*** ~~ normal2

This is a [link **with** formatting](https://example.org)

====
This is not a header

That's all ...

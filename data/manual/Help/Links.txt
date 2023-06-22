Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.6
Creation-Date: 2021-01-19T20:44:59+01:00

====== Links ======

You can either link pages or URLs. URLs are recognized because they start with e.g. "''https://''" or "''mailto:''". Page names can contain ':' characters to separate the page name from parent pages.

* Links containing a '/' are considered links to external files
* Links that start with a ':' are resolved from the top level of the notebook
* Links that start with a '+' are resolved as sub-pages below the current page
* Links that start with a '#' are resolved as links within the page to a heading or an object
* Links that contain a '?' are interwiki links, see below.
* All other links are resolved within the path from the root to the current page

You can make any text into a link, thus the link you see and what it links to do not have to be the same. You can use the "//Edit//->//Link//" menu item to modify a link.

Links can also be auto-formatted when typing, see [[Auto Formatting]] for more details


==== Relative links ====
All links to other pages are relative to the current page unless they start with an ":" character. Zim first looks in the same section as the current page and if the name is not found, it searches all the parent sections. The rule is that it will check all pages that share a common parent with the current page bottom-up and match the first page with the right name. If you want to link to a child of a page that has a common parent you can link it using a relative path from the top page that does have a shared parent.

For example, you have a page "''Zim:Examples:Linking:Relative''" now you just use "''Absolute''" to link to "''Zim:Examples:Linking:Absolute''", but you also use "''Examples:Calendar''" to link to "''Zim:Examples:Calendar''". This link works because the first part of the link ("''Examples''") is resolved relatively in the tree above the current page.

To create relative links to a sub-page of the current page, start the link with an "''+''".

Note that when inserting the link by [[Auto Formatting]] the link must have at least 2 letters in the first part of the link to avoid linking strings like e.g. "10:20PM". Also see [[Pages]] for more information on page names.


==== Link to a heading or object ====
To link to a heading or an object you can use "''#heading-id''" within the same page or "''pagename#heading-id''" from another page.

Headings have an implicit id which consist of the heading text in lowercase with spaces replaces by "-" and all special characters removed. For example the heading of this section can be links as [[#link-to-a-heading-or-object]].

Objects like images and other inline objects can have an explicit "id" attribute, which can be used in the same way.

Finally there is a special "anchor" object to place a link anywhere in the text or to e.g. set an explicit id for a heading. This can be inserted by typing "''##name''" and is rendered like this: {{id: name}} .


==== File Links ====
You can link to files from zim. File names always need to contain a "''/''" character (even if your operating system uses another path separator). You can link relative to your home directory using "~/foo"  or relative to the page using "./foo". When you want to "attach" a file to a page you can use "//Tools//->//Open folder//" to open the file browser in the appropriate directory. Once you have copied or moved the file to this directory you can drag-and-drop from your file browser to the zim page, this will create a link.

File links starting with "''/''", like "''/foo''" will be relative to the filesystem root, or to the Document Root, if you have one set in the [[Properties]]. If a Document Root is set, the only way to link to files outside this root is to use "''file:///''" URIs.

Proper file URIs for files on the local filesystem should always start with either "''file:///''" or "''file://localhost/''".  URIs starting with "''file:/''" are technically invalid but will be interpreted as a local file. URIs starting with "''file://''" suggest a remote file following the "''file://host/share/''" syntax, these will be interpreted as a link to a "windows" share drive.

==== Links to share drives ====
"Windows" share drives or samba shares under Linux can be linked in different ways:

'''
smb://host/share/path
file://host/share/path
\\host\share\path
'''


The first form, using "''smb://''" is recommended because it is most explicit, while the third form will be most recognizable for windows users.

===== Interwiki =====
There is a list of pre-defined urls in "''share/zim/urls.list''" which lists most commonly used online wikis. These urls can be referred to by a keyword so you don't have to type the full url every time; also you can update all links to a certain wiki by changing the url in the file. Have a look at the list to get an idea of how to use this.

This link for example goes to wikipedia.org and opens the page "wiki": [[wp?wiki]]

To add your own urls use "''~/.local/share/zim/urls.list''". All types of urls which are supported by zim can be added. Consider adding "''file://''" urls for directories you refer often from zim. See [[Config Files]] for more details.

The zim notebooks you added in the "Open notebook" dialog are automatically recognized as interwiki names. So you can link to notebooks using either their name or their interwiki keyword (both case insensitive). The interwiki keyword is for a specific notebook can be set in the [[Properties]] dialog.

===== Back links =====
"Back links" are the reverse of normal links. For example when page //A// links to page //B// then page //B// will have "back link" to page //A//. The list with back links is the answer the to question "What links here".

To view which pages link here you can open the "Search Back links" menu item (//Search//->//Search Back links//) or use the [[Plugins:BackLinks Pane|BackLinks Pane]] plugin.

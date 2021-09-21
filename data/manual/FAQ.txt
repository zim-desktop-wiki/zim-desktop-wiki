Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.6
Creation-Date: Wed, 08 Jul 2009 23:26:20 +0200

====== FAQ ======

Mail [[jaap.karssenberg@gmail.com|me]] if you have questions that you would like to see answered below.

===== How do I create a new page? =====
You can just link non-existing pages. If you follow such a link the page will be created automatically when needed.

===== How do you close these "tabs" ? =====
Uhm, if you mean the buttons above your page, technically they are not tabs but a path bar keeping track of your history or recent pages. The buttons in this bar map to pages in your browse history, not to open pages or something like that. You can not "close" something that is in your history. To change the style of this bar, or hide it completely, go to the "//View"// -> "//Pathbar//" menu item.

===== How do I organize my pages in a tree structure? =====
You can organize your pages by grouping them into sections. To do so you put pages as sub-pages of a top-level page. The "'':''" character is used to separate the page levels in the page name. Thus if you link to "''foo:bar''" you will link to the page called "bar" as a sub-page of the "foo" section. Just link a non-existing page and follow the link to create it. See [[Help:Pages|Pages]] for more information.

===== Why are some pages in the index grayed out? =====
These are pages that are linked by other pages but do not (yet) contain text. You can edit them to make them regular pages or check the pages linking them.

===== Why do some pages not disappear from the index after deleting them? =====
The index keeps pages that are linked by other pages even if you delete them. To completely remove them you also need to change any page linking them.

===== I pasted a shell script / C code / ... and it looks all mangled up - is this a bug ? =====
No, zim uses wiki formatting to save text, so some sequences of special characters will be interpreted as text formatting. This is enabled on purpose to let users type in wiki sequences directly. The downside is that when you include computer code or other text with many special characters it might get interpreted while that is not what you wanted. To avoid this either use the [[Plugins:Source View|Source View plugin]] or verbatim formatting. To paste directly with verbatim formatting there is a menu item in the context menu "Paste As Verbatim".

===== I would like zim to hide in the system tray. =====
There is a [[Plugins:Tray Icon|Tray Icon plugin]] which can be enabled from the Preferences dialog.

===== I would like to start zim hidden in the system tray. =====
You can call the [[Plugins:Tray Icon|Tray Icon plugin]] with the command "''zim --plugin trayicon''"

===== Can I make zim appear with a global keybinding? =====
By default, zim will only run a single instance of each notebook. Trying to open the same notebook again will just pop the corresponding window to the foreground. So you can set a default notebook (see [[Help:Notebooks|Notebooks]]) and just make a global key binding run the command "''zim''".

===== How do I publish content from zim to my webpage? =====
See [[Usage:Publishing|Publishing]] for some tips

===== Can I change the colors used for links, underline etc. ? =====
Yes. Copy "''/usr/share/zim/style.conf''" to "''~/.config/zim/''" and edit as you see fit. See the [[Help:Config Files|Config Files]] page for the syntax of this file.

===== Can I have encrypted notebooks? =====
Zim notebooks do not support encryption or password protection natively. However, you can use for example [[https://www.arg0.net/encfs|encfs]] to encrypt your notebooks.

===== Can I have full calendaring in zim? =====
Well, if you want to, you can use zim as your agenda. However, the Calendar feature is more intended to keep various kinds of journals or logbooks. I'm very hesitant to add calendaring features because these are usually tied to email applications. I admit that it would be really cool to link notes, emails and appointments, but I have no plans to extend zim to become an email reader.

===== How do I change the font size of the side pane =====
You can change this by modifying the gtk css file, see [[Help:Config Files|Config Files]] for details.

===== Does it run on Windows? =====
Yes, it does. See the download page on the website for more notes on installing on the win32 platform.

===== Does it run on OS X? =====
Yes, it does. See the install instructions on our [[https://zim-wiki.org/install.html|webpage]], or check in the [[https://www.zim-wiki.org/wiki/|zim documentation wiki]] for additional tips how to install it.

===== I want to move/backup/synchronize a zim notebook. Which files do I need to take care of? =====
The visible files in the notebook folder contain all data of notes and [[Help:Attachments|attachments]].

===== What is the hidden .zim folder in my notebook folder? =====
The hidden .zim folder contains only caches and GUI state. It doesn't contain any information that can not be recreated on the fly.

===== How can I synchronize a zim notebook? =====
By synchronizing all visible files in the notebook. E.g. by putting the zim notebook in a dropbox share.

===== Can multiple people collaborate using a zim notebook ? =====
Zim is written as a "single user" program, so it is not intended for multiple people using the same notebook. However, it can be used with version control like Bazaar, Git or Mercurial. This way multiple users can work on the same notebook and merge their changes. See the [[Plugins:Version Control|Version Control plugin]].


===== How do I change the Gtk theme? =====
On a Linux desktop, you can probably do this via your settings manager.

Windows and macOS users please see the section "Gtk configuration" in [[Help:Config Files|Config Files]]


===== I have a useful trick or tip. How can I share it with other users? =====
You can have a look at the [[https://www.zim-wiki.org/wiki/|zim documentation wiki]]. It has a section dedicated to tricks and tips. And you can post in the "show and tell" section of discussion forum at https://github.com/zim-desktop-wiki/zim-desktop-wiki/discussions.

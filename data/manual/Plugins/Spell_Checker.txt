Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.4

====== Spell Checker ======

This plugin adds inline spell checking for zim. It has a preference setting to determine the language used for spell checking. If this is not set, the system default is used.

**Dependencies:** This plugin requires either of these libraries: "''gtkspellcheck''", "''Gspell''", or "''gtkspell''"; the first one is preferred as it seems more reliable and if multiple are installed, this is the one used.

To install "''gtkspellcheck''":
* On Ubuntu or Debian systems installing the package "python3-gtkspellcheck" will meet these dependencies.

To install "''Gspell''":
* On Ubuntu or Debian systems installing the package "gir1.2-gspell-1" will meet these dependencies.

To install "''gtkspell''":
* On Ubuntu or Debian systems installing the package "gir1.2-gtkspell3-3.0" will meet these dependencies.


===== Options =====
The options **Default Language** specifies the language to use for the spell checking. Languages should be specified as language codes, e.g. for Dutch, you would set "nl" or "nl_NL". If the option is not set, the system default will be used.

===== Dictionaries =====
The libraries do not always come with all dictionaries installed. If no dictionary is found for your language zim will give an error when loading this plugin. In this case dictionaries have to be installed separately.

There are multiple dicutionary packages available. The GSpell documentation states: "At least on GNU/Linux, it is better to install hunspell. aspell can be considered deprecated and doesn't work well with gspell. If both hunspell and aspell are installed, Enchant prefers hunspell by default." (Enchant is the backend used at least by both gtkspellcheck and Gspell.)



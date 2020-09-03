Changes for zim
===============
Jaap Karssenberg <jaap.karssenberg@gmail.com>

This branch is the Python rewrite and starts with version 0.42.
Earlier version numbers for zim correspond to the Perl branch.

##  0.73.2 - Fri 24 Jul 2020
* Add "show debug log" menu item
* Add missing "triangle" icons for windows installer
* Include helper to spawn external processes for windows installer
* Fix dropdown namespace autocomplete in move-page dialog
* Fix wiki parser for case of nested URL
* Fix ParseTreeBuilder interface for python3.9
* Add debug output for drag-and-drop workaround
* Fix popup menu in attachment browser plugin
* Fix warnings during export for "page.meta"
* Fix on-preferences-changed for tableofcontents plugin

##  0.73.1 - Fri 19 Jun 2020
* Fix regression for opening single instance
* Fix exception on toggle format
* Fix failing tests due to change in sorting python3.8
* Make robust for deprecation of cElementTree in python3.9
* Improve tmpdir usage by using tempfile.mkdtemp()

##  0.73.0 - Sat 06 Jun 2020
* Add ability to combine formatting styles in editor
* Improve URL and link parsing to look for matching brackets
* Reduce the number of `-` needed to auto-format a horizontal line
* Allow typing bullet after e.g. checkbox to replace it
* Add autoformat for sub- and super-script by typing `^..` and `_{..}`
* On autoformat headings also strip trailing `=`
* Fix issue with lost formatting when using spellchecker
* Add support for "paragraph-background" property in style.conf
* Improve keyboard behavior of find bar in editor
* Swap the layout in the InsertDateDialog
* Allow re-arranging side pane tabs by drag and drop
* Add option to automatically collapse sections in the pageindex
* Fix regression for inserting links on "Attach file" and moved this
  function to the Insert menu
* Merge MovePageDialog and RenamePageDialog into a single dialog
* Fix behavior when renaming non-existing "placeholder" pages
* Add workaround for drag-and-drop issue #390
* Whitelist image formats in latex export to avoid invalid image types
* Add MacOS menubar plugin & fix for main menu mnemonics in MacOS
* Give temporary directories unique names to improve robustness
* Support TEXTDOMAINDIR evironment variable to set locale directory
* Improve folder checks for automount feature
* Improve window colors in distraction free mode
* Add option to set the wrap-mode in sourceview
* Add theme choice for the source view plugin
* Add "private" switch to server command for commandline usage
* Add authentication support to web server
* Add template selection option to web server dialog
* Add option for fontsize to table of contents plugin
* Add option to show horizontal lines in table of contents

##  0.72.1 - Wed 01 Jan 2020
* Update translations & documentation

##  0.72.0 - Thu 29 Aug 2019
* Improve pathbar with "linked" visual design
* Improve statusbar visual style
* Change behavior for lists with mixed bullets
* Add configuration of keybindings to preferences dialog
* Support gnome-screenshot in the insert screenshot plugin
* Save size of secondary page window
* Add option for linenumbers option in insert code block dialog
* Add option to display date column in tasklist side pane
* Add warnings if locale does not support unicode
* Make SVG thumbnail support configurable
* Fix bug for insert equation and other objects
* Fix use of escape sequence in table cells
* Fix tasklist view for multiple dates in task
* Fix "apply heading" to strip list formatting
* Make ToC plugin update instead of refresh on save
* Fix issue with not-unique headings in tableofcontents
* Fix bugs in auto insert bullet at newline

##  0.71.1 - Thu 23 May 2019
* Fix robustness for OSError on process startup
* Fix for popup menu on page index for Gtk < 3.22
* Updated translations

##  0.71.0 - Thu 25 Apr 2019
* Fix "spill over" between translation files
* Fix use of popup menus
* Hack to work around textview glitches embedded objects
* Make indexer recover from duplicate page names
* Fix recovery of broken index file on startup
* Restore New Sub Page for index context menu
* Let customtools replace autoselected words and insert
* Fallback encoding when calling external applications
* Hide pathbar in distraction free mode
* Merge fix for unicode completion in dialogs
* Remember cursor position on reload
* Fix inlinecalculator plugin
* Update Gtk prerequisite version to 3.18
* Updated Russian translation

##  0.70 - Thu 28 Mar 2019
* Ported zim to use Python3 & Gtk3
* Refactored application framework, all windows run single process now with
  single plugin manager and preferences manager
* Refactored plugin extension loading code and added functions to find
	extensions and actions
* Removed the notebook "profile" properties
* Plugins now can use notebook properties to store settings per notebook
* The page index side pane and the pathbar are now plugins
* Redesign journal plugin sidepane view and remove dialog
* Renamed "calendar" plugin to "journal"
* Removed OSX menubar plugin
* Image generator plugins now are "inserted objects"
* Workaround for missing clipboard.set_with_data()
* Improved speed of test suite and refactored test constructs
* Support flatpack-spawn to execute processes
* Critical fix for updating links on move page and rename page
* Critical fix for parsing headers when page has no title
* Fix page index issue on delete page

##  0.69 - Sun 16 Dec 2018
* Performance improvements for indexing large notebooks
* Performance improvement for auto-completion of page names in dialogs
* Updated translations from launchpad

##  0.68 - Sat 17 Mar 2018
* Critical fix for updating links on move page and rename page
* Critical fix for rename page and indexing on case-insensitive file systems
  (like windows)
* Fix for regression in tasklist option to _not_ regard all checkboxes as tasks
  -- Fabian Stanke
* Fix for egression in index navigation with previous page and next page
* Fix for memory leak in spell checker plugin -- Alexander Meshcheryakov
* Fix issues with multi-line selections in linesorter plugin
* Fix bug with opening notebook list from tray icon
* Fix bug with "-s" commandline argument for exporting
* Fix bug with importing attachments in quicknote plugin commandline use
* Pathbar now reveals more path elements in case of ambiguous pages -- Robert Hailey
* Add "font" property for use in "styles.conf"
* Add "navigation.home" to template parser for export -- Rolf Kleef
* Version control plugin updated to better handle git staging -- Paul Becker
* Extend interface for "image generator" plugins - Robert Hailey
* Code cleaned up to be a bit PEP8 compliant and more future proof for python3
  conversion -- Christian Stadelmann

##  0.67 - Mon 10 Jul 2017
* Critical fix for missing page headers & remembering custom headers
* Critical fix by removing dependency on threading for index and socket handling
  - Hidden option to also do autosave without thread to test further issues
* Critical fix for handling unicode file names on windows
* Fix issue where config values go missing if not used
* Fix error for file shortcuts in various dialogs
* Restored macOS integration using a plugin
* Shorter socket name to avoid os specific error on OS X
* More robustness for socket errors, fallback to --standalone automaticlly
* More robustness at startup when default notebook went missing, fallback to --list
* More robustness in preferences dialog when plugins give exceptions
* More robustness for invalid dates in tasklist parser
* Merge patch to add accelerators for bookmarks
* Updated build process for windows installer
* Fix indexing errors on move/rename page
* Fix regression in close-page when autosave ongoing
* Fix regression drag-n-drop index pane
* Fix regression for keybindings in index pane
* Fix regressions for attaching files
* Fix regression for opening folders
* Fix regression in opening inter-wiki links
* Fix regression in custom tools
* Fix regression in completion of page name in dialog entry
* Fix regression in quicknote "--attachments" option
* Fix regression for quicknote plugin due to process management
* Fix regression in date format for recentchanges dialog
* Fix regression in custom tool execution
* Fix for unicode in auto-linking
* Fix for unicode in arithmetic plugin
* Fix "insert image" also inserting a text link
* Fix search regex for chinese language to not match whitespace for start/end of word
* Fix for table editor plugin when sorting rows
* Fix for wrong usage of escapes in latex export for verbatim blocks


##  0.66 - Fri 28 Apr 2017
* Multiple notebooks run as single process now to reduce multi-process
  complexity - more robust startup, reduce need for "--standalone"
* SQLite indexer re-written to fix long standing bugs and design flaws
  with indexing
* Improved performance tag filtering in side pane
* Detect pages have changed on disk, even when page present in cache
* Bug fix for drag-n-drop of text within the editor
* New checkbox type available for "moved task" for journal workflow
* Context menu defined for checkboxes
* Horizontal lines "<HR>" added to wiki syntax -- Pavel_M
* Pathbar buttons can now also be used to insert page links by drag-n-drop
  -- Klaus Holler
* "search in section" added to context menu for pages
* "search backlinks" added to context menu for pages -- Volodymyr Buell
* Keyboard navigation of plugin tab in preferences dialog -- Jens Sauer
* Allow "mailto:" links contain arguments like "?subject="
* Tasklist plugin: now also available embedded in side pane
* Tasklist plugin: new syntax for including due and start dates
* Tasklist plugin: new formatting priority column including deadlines
* Tasklist plugin: new "flat list" mode to only see lowest level tasks
* Tasklist plugin: removed support for "next" label
* Tasklist plugin: dialog now remembers sorting -- Jonas Pfannschmidt
* Versioncontrol plugin: git: removed global "git add", instead stage
  individual files
* Versioncontrol plugin: fossil: fix for fossil "addremove"
* Attachment browser: bug fix for drag-n-drop
* Linesorter plugin: added keybindings to move / duplicate / delete lines
  -- Johannes Kirschner
* Sourceview plugin: bug fix to make export via commandline also use
  objects -- Alex Ivkin
* Sourceview plugin: bug fix to follow editable state of parent window
  -- Jan Taus
* Bookmarks plugin updates -- Pavel_M
* Tableeditor plugin: bug fix for links -- Sašo Živanović
* Linkmap plugin: bug fix "unexpected char '-'"
* Arithmic plugin: bug fix to allow negative numbers -- TROUVERIE Joachim
* Dev: Templates are now translatable, using "gettext()" -- Jens Sauer
* Dev: Index API completely changed, see tasklist for a plugin example
* Dev: New module for file-system interaction, to be used in new code
* Dev: New parsing strategy based on tokenlist, used for tasklist parser
* Dev: Defined notebook API for concurrent operations in gtk main loop
* Dev: Simplified SignalEmitter code
* Packaging: removed support for maemo build - code went stale
* Packaging: make package build reproducible -- Reiner Herrmann
* Added translations for: Amharic, Arabic, Basque, and Portuguese


##  0.65 - Sun 01 Nov 2015
This release fixes two critical bugs in version 0.64:
* <Control> keybindings fail for older gtk versions, and in particular
  for the <Control><Space> keybinding
* The table editor tends to drop columns of content in the precences
  of empty cells


##  0.64 - Tue 27 Oct 2015
* Bookmark plugin - by Pavel M
* Updated spell plugin to allow using gtkspellcheck as backend
* Updated attachmentbrowser plugin with new thumbnailing logic
* Speed up of sqlite indexing
* Updated support for OS X - by Brecht Machiels
* Bug fixes for the Fossil version control support
* Bug fixes for locale in strftime and strxfrm functions
* Bug fix to avoid overwriting the accelmap config file


##  0.63 - Sat 13 Jun 2015
* Table plugin - by Tobias Haupenthal
* Support for Fossil version control - by Stas Bushuev
... Many bug fixes


##  0.62 - Tue 30 Sep 2014
Bug fix release
* Fixed broken Source View plugin
* Fixed Tray Icon plugin for Ubuntu
* Fixed bug with Caps Lock on windows
* Fixed behavior of New Page dialog
* Fixed status parsing for Git backend
* Fixed bug with CamelCase parsing for Persian & Arabic script
* Fixed parsing of numbered list character to be robust for Chinese characters
* Fixed bug with www server dialog
* Fixed bug in Go Child Page action
* Fixed export using the S5 slideshow template - now splits by heading
* Fixed bug in indexing for python 2.6
* Fixed bug in Open Notebook dialog when selecting current notebook
* Changed lookup path for 3rd party plugin modules - now uses XDG path
* Merged patch to support more screenshot tools in the Insert Screenshot
  plugin - Andri Kusumah
* Updated Sort Lines plugin to use natural sorting for unicode
* Added control for handling of line breaks in HTML export
* Changed rendering of checkboxes in HTML export
* Merged patch to set image size for GNU R plugin - Olivier Scholder
* Added control to toggle full page name in Tag index view
* Added handling of SIGTERM signal

##  0.61 - Thu 31 Jul 2014
* Full refactoring of code for parsing and processing wiki syntax
  making parser easier to extend and document interface more scalable
* Full refactoring of code for plugin framework making plugins more
  flexible by defining decorators for specific application objects
* Full refactoring of code for exporting pages from zim
  - Now supports MHTML export format
  - Supports exporting multiple pages to a single file
  - Supports recursive export of a page and all it's sub-pages
  - Templates now support many more instructions and expressions
* Full refactoring of the code for parsing commandline commands and
  initializing the application
* New config manager code to make parsing and handling of config files
  more robust
* Merged new plugin for editing sequence diagrams by Greg Warner
* Improved the ToC plugin with floating widget
* Fixed unicode issue when calling external applications, and in
  particular for the hg and git commands
* Fixed support for unicode CamelCase word detection
* Fixed bug on windows with unicode user names in background process
  connection
* Changed "tags" plugin to show full page paths in the pre-tag view
* Added option for custom commands to replace the current selection
* Added keybindings for XF86Back and XF86Forward
* Many small fixes & patches from various persons that I forgot about *sorry*
* Added Finnish translation

##  0.60 - Tue 30 Apr 2013
* In this release the required python version is changed from 2.5 to 2.6 !
* Added a Recent Changes dialog and a Recent Changes pathbar option
* Added search entry to toolbar
* Added function to attachment browser plugin to zoom icon size
* Added new template by Robert Welch
* Critical bug fix for using templates that have a resources folder
* Fix for week number in Journal plugin page template (again)
* Fix for focus switching with distraction free editing plugin
* Fix for handling BOM character at start of file
* Fixed quicknote dialog to ask for confirmation on discard
* Fix to allow calling executables that do not end in .exe on windows
* Fix for various typos in the manual by Stéphane Aulery
* Removed custom zim.www.Server class in favor of standard library version
* New translations for Korean and Norwegian Bokmal

##  0.59 - Wed 23 Jan 2012
* Critical bug fix in pageview serialization
* Fix for inheritance of tags in tasklist - Epinull
* Fix for customtools dialog - Epinull
* Fix for week number in Journal plugin page template

##  0.58 - Sat 15 Dec 2012
* Added new plugin for distraction free fullscreen mode
* Added options to limit tasklist plugin to certain namespaces -
Pierre-Antoine Champin
* Added option to tasklist plugin to flag non-actionable tasks by a special tag
* Added prompt for filename for Insert New File action
* Added template option to list attachments in export
* Added class attributes to links in HTML output
* Added two more commandline options to quicknote plugin
* Made sidepanes more compact by embedding close buttons in widgets
* Critical fix for restarting zim after a crash (cleaning up socket)
* Bug fix for search queries with quoted arguments
* Bug fix for use of tags in the tasklist plugin
* Bug fix for wiki format to be more robust for bad links
* Bug fix for latex format to not use file URIs in \includegraphics{}
* Bug fix for including latex equations in latex export
* Bug fix list behavior checkboxes and numbered lists
* Fix first day of week locale for calendar plugin - based on patch by
Leopold Schabel
* Fix for handling "file:/" and "file://" URIs in links - see manual for details
* Fix for windows to not open consoles for each external application - klo uo
* Fix for windows to put config files under %APPDATA% - klo uo
* Fix to have "update heading" toggle in rename dialog more
intelligent - Virgil Dupras
* Fix to make template errors report relevant error dialogs
* Fix for search and replace whitespace in pageview
* Various small fixes

##  0.57 - Mon  8 Oct 2012
* Ported zim background process to use the multiprocessing module
  - this fixes app-indicator issues under Ubuntu Unity
  - adds support for quicknote and other plugins on Windows
* Reworked application framework and "open with" dialog, now also
  allows to set applications per URL scheme
* New plugin for using GNU Lilypond to render music scores - Shoban Preeth
* New Zeitgeist plugin - Marcel Stimberg
* Added template method to iterate days of the week for a calendar page
* Added pythonic syntax to access dicts to template modules
* Added tasklist option to take into account a Mon-Fri work week
* Fixed start of week and week number first week of the year for calendar plugin
* Added "untagged" category to task list
* Fixed strike out TODO label showing up in task list
* Added template editor dialog
* Added support for "forward" and "back" mouse buttons
* Added support for exporting to ReST - Yao-Po Wang
* Added new option to create and insert new attachments based on file template
* Added an argument to the quicknote plugin to import attachments
* Added icons per mimetype to the attachmentbrowser
* Added statusbar button for attachment browser
* Added monitors to watch attachment folder for updates
* Fix drag&drop on non-existing folder in attachment browser
* Fix drag&drop for attachment folder on windows
* Made location of plugin widgets in side panes configurable
  and reworked key bindings for accessing side panes and toggling them
* Made tags plugin to revert to standard index if no tag is selected
* Page completion now matches anywhere in the basename -- patch by Mat
* Patch to use sourceview in imagegenerator dialog - Kevin Chabowski
* Fix for insert symbol dialog to insert without typing a space
* Made image data pasted as bmp convert to png to make it more compact
* Critical bug fix for version control plugin
* Critical bug fix for xml.etree.TreeBuilder API for python 2.7.3
* Bug fix for exceptions in index - Fabian Stanke
* Bug fix for interwiki links
* On windows fix for bug when home folder or user name contain non-ascii characters
* Fixed help manual opens in compiled windows version
* Fixed locale support on windows
* Added translations for Brazilian Portuguese and Romanian


##  0.56 - Mon  2 Apr 2012
* Merged support for Git and Mercurial version control backends -
  Damien Accorsi & John Drinkwater
* Merged plugin for "ditaa" diagrams - YPWang
* Merged patch for different configuration profiles, allowing per
  notebook configuration of plugins, font etc. - Mariano Draghi
* Added drag & drop support for the Attachment Browser plugin
* Made sidepane and tagcloud remember state
* Fixed critical bug for opening email adresses without "mailto:" prefix
* Fixed bug where context menu for page index applied to the current page
  instead of the selected page
* Added a Serbian translation

##  0.55 - Tue 28 Feb 2012
* Numbered lists are now supported
* The index now has "natural" sorting, so "9" goes before "10"
* Added new plugin to show a Table Of Contents per page, and allows modifying the outline
* Added Markdown (with pandoc extensions) as an export format
* New context menu item "move text" for refactoring text to a new page
* Tasklist now supports a "next:" keyword to indicate dependencies,
  and it can hide tasks that are not yet actionable
* Made zim taskbar icons and trayicon overloadable in theme - Andrei
* Fixed behavior of Recent Pages pathbar in cases where part of the history is dropped
* Fixed behavior of the Search dialog, it no longer hangs and also allows cancelling the search
* Fixed bug where replacing a word (e.g spell correction) could drop formatting
* Fixed behavior of case-sensitive rename on a case-insensitive file system (windows)

##  0.54 - Thu 22 Dec 2011
Bug fix release with minor feature enhancements
* Added mono icons for the Ubuntu Unity panel
* Tasklist plugin now supports hierarchic nested tasks
* Added "automount" plugin to automatically mount notebook folders
* Interwiki lookup now goes over all urls.list files in the path
* Fixed bug that prevented clicking links in read-only mode
* Fixed bug for parsing relative paths to parent pages e.g. in drag and drop
* Fixed bug causing the index to jump with every page selection
* Fixed bug causing the icon for custom tools to be missing in the toolbar
* Fixed bug for drag and drop of files on windows
* Fixed bug causing task list to reset when page is saved
* Fixed autocomplete for page entry in quicknote
* Fixed error in "you found a bug" error dialogs :S
* Fixed issue in test suite for loading pixbufs
* Added translation for Galician

##  0.53 - Mon 19 Sep 2011
* Cosmetic updates to entry widgets, the page index, the insert date dialog,
  and the tasklist dialog
* Updated the find function to properly switch focus and highlight current
  match even when text does not have focus - Oliver Joos
* Added function to remember the position of the main window across sessions
  and the position of dialog within a session - Oliver Joos
* Added "interwiki keyword" to give shorthand for linking notebooks - Jiří
  Janoušek
* Added template function to create a page index - Jiří Janoušek
* Added support to include additional files with a template - Jiří Janoušek
* Added preference for always setting the cursor position based on history
  or not
* Added feature so images now can have a link target as well - Jiří Janoušek
* Refactored index to do much less database commit actions, resulting in
  performance gain on slow storage media
* Added "print to browser" button in the tasklist dialog
* Added "--search" commandline option
* Added feature for calendar plugin to use one page per week, month, or year
  instead of one page per day - Jose Orlando Pereira
* Added feature to have implicit deadline for tasks defined on a calendar
  page - Jose Orlando Pereira
* Added new plugin for evaluating inline arithmetic expressions - Patricio Paez
* Added support for plugins to have optional dependencies - John Drinkwater
* Added hook so plugins can register handlers for specific URL schemes
* Upgraded test suite to unittest support shipped with python 2.7
* Increased test coverage for main window, dialogs, and image generator plugins
* Many small typo fixes and code cleanup - Oliver Joos
* Extensive updates for the developer API documentation - now using epydoc
* Made file paths in config file relative to home dir where possible in order
  to facilitate portable version (e.g. home dir mapped to USB drive)
* Build code updated to build new windows installer and support for portable
  install - Brendan Kidwell
* Fixed build process to hardcode platform on build time (maemo version)
* Fixed bug in notebook list, causing compiled version to be unable to set
  a default notebook (windows version)
* Fixed bug with copy-pasting and drag-n-drop using relative paths
* Fixed bug allowing to click checkboxes in read-only mode
* Fixed several possible exceptions when moving pages
* Fixed execution of python scripts on windows - Chris Liechti
* Fix to preserve file attributes (like mtime) when copying attachments
  - Oliver Joos
* Fixed path of checkbox images in html export - Jiří Janoušek
* Fix for indexing error in scenario with external syncing (e.g. dropbox)
* Fix for latex output to use "\textless{}" and "\textgreater{}"
* Fixed Maemo window class, and python 2.5 compatibility - Miguel Angel Alvarez
* Fixed unicode usage in template module - Jiří Janoušek
* Fixed error handling for errors from bzr in versioncontrol plugin
* Fixed error handling for errors due to non-utf-8 encoded text in pages



##  0.52 - Thu 28 Apr 2011
Bug fix release
* Fixed a critical bug in the "Add Notebook" prompt for the first notebook on
  a fresh install and two minor bugs with the ntoebook list - Jiří Janoušek


##  0.51 - Tue 19 Apr 2011
* Fixed critical bug with resizing images - Stefan Muthers
* Fixed bug preventing resizing of text entries in dialogs
* Fixed bug disabling auto-completion for page names in dialogs
* Fix so cancelling the preferences dialog will also reset plugins
  - Lisa Vitolo
* Fix to switch sensitivity of items in the Edit menu on cursor position
  - Konstantin Baierer
* Fix to handle case where document_root is inside notebook folder
  - Jiří Janoušek
* Fixed support for interwiki links in export
* Fixed "Link Map" plugin to actually support clicking on page names in the map
* Fixed copy pasting to use plain text by default for external applications
  added preference to revert to old behavior
* Disable <Alt><Space> keybinding due to conflicts with internationalization
  added hidden preference to get it back if desired
* Added support for organizing pages by tags - Fabian Stanke
* Added feature to zoom font size of the page view on <Ctrl>+ / <Ctrl>-
  - Konstantin Baierer
* Added support for system Trash (using gio if available)
* Added Calendar widget to the "Insert Date" dialog
* Added plugin to sort selected lines - NorfCran
* Added plugin for GNUplot plots - Alessandro Magni


##  0.50 - Mon 14 Feb 2011
Maintenance release with many bug fixes. Biggest change is the refactoring
of input forms and dialogs, but this is not very visible to the user.

* Added custom tool option to get wiki formatted text
* Added option to Task List plugin to mix page name elements with tags
* Added style config for linespacing
* Cursor is now only set from history when page is accessed through history
* Updated latex export for verbatim blocks and underline format
* Added basic framework for plugins to add widgets to the main window
* Notebook list now shows folder path and icon - Stefan Muthers
* Folder last inserted image is now remembered - Stefan Muthers
* Preview is now shown when selecting icons files - Stefan Muthers
* Image paths are now made relative when pasting image an file - Jiří Janoušek
* Image data is now accepted on the clipboard directly - Stefan Muthers
* Added overview of files to be deleted to Delete Page dialog to avoid
  acidental deletes
* Added traceback log to "You found a bug" error dialog
* Fixed critical bug for windows where zim tries to write log file
  to a non-existing folder
* Fixed critical bug where text below the page title goes missing on rename
* Fixed behavior when attaching files, will no longer automatically overwrite
  existing file, prompt user instead - Stefan Muthers
* Fixed bug when opening notebooks through an inter-wiki link
* Fixed support for month and year pages in Calendar namespace
* Fixed support for wiki syntax in Quick Note dialog when inserting in page
* Fixed bug in Task List plugin where it did not parse checkbox lists with a
  label above it as documented in the manual
* Fixed bug with custom template in export dialog - Jiří Janoušek
* Fixed bug with style config for tab size
* Fixed many more smaller bugs
* Rewrote logic for indented text and bullet lists, fixes remaining
  glitches in indent rendering and now allow formatting per bullet type
* Refactored part of the Attachment Browser plugin, no longer depends
  on Image Magick for thumbnailing and added action buttons
* Refactored code for input forms and decoupled from Dialog class
* Refactore History class to use proper Path objects
* Added significants amount of test coverage for dialog and other interface
  elements
* Package description of zim was rewritten to be more readable
* Added translation for Danish


##  0.49 - Tue 2 Nov 2010
* Added experimental Attachment Browser plugin - by Thorsten Hackbarth
* Added Inline Calculator plugin
* Made file writing logic on windows more robust to avoid conflicts
* Fixed bug with unicode characters in notebook path
* Fixed 'shared' property for notebooks
* Patch to update history when pages are deleted or moved - by Yelve Yakut
* Patch backporting per-user site-packages dir for python 2.5 - by Jiří Janoušek
* Fix for bug with spaces in links in exported HTML - by Jiří Janoušek
* Fixed bug forcing empty lines after an indented section
* Patch for indenting in verbatim paragraphs - by Fabian Stanke
* Fixed bug with unicode handling for file paths
* Added names for pageindex and pageview widgets for use in gtkrc
* Patch to jump to task within page - by Thomas Liebertraut
* Added option for setting custom applications in the preferences
* Fixed printtobrowser plugin to use proper preference for web browser
* Added default application /usr/bin/open for Mac
* Imporved behavior of 'Edit Source'
* Added checkbox to quicknote dialog to open the new page or not
* Added support for outlook:// urls and special cased mid: and cid: uris
* Added translations for Hungarian, Italian and Slovak


##  0.48 - Thu 22 Jul 2010
* Added support for sub- and superscript format - by Michael Mulqueen
* Updated the export dialog to an Assistant interface
* Renamed "Create Note" plugin to "Quick Note"
* Improved the "Quick Note" plugin to support appending to pages and
  support templates
* Fixed webserver to be available from remote hosts and to support files
  and attachments
* Merged support for Maemo platform with fixes for zim on a small screen
  - by Miguel Angel Alvarez
* Updated zim icon and artwork
* Several fixes for latex export - by Johannes Reinhardt
* Fixed inconsistency in formatting buttons for selections
* Fixed bug that prevented adding custom tools without icon
* Fixed bug with deleting directories on windows
* Added translations for Catalan, Croatian and Slovak

##  0.47 - Sun  6 Jun 2010
Big release with lots of new functionality but also many bug fixes

* Significant performance improvements for the page index widget
* Task list plugin now uses the index database to store tasks, this makes
  opening the dialog much faster. Also the dialog is updated on synchronous
  as soon as changes in the current page are saved.
* Added support for "TODO" and "FIXME" tags in task list plugin, as a special
  case headers above checkbox lists are supported as well
* Added "create note" dialog to quickly paste text into any zim notebook,
  it is available from the trayicon menu and can be called by a commandline
  switch
* Support added for new "app-indicator" trayicon for Ubuntu 10.4
* Added support to start trayicon by a commandline switch
* Option added to reformat wiki text on the fly (Johannes Reinhardt)
* Attach file dialog can now handle multiple files at once (Johannes Reinhardt)
* Layout for linkmap improved by switching to the 'fdp' renderer
* Added new plugin "Insert Symbols" for inserting e.g. unicode characters
* Added new plugin to insert and edit plots using GNU R (Lee Braiden)
* Added scripts needed to build a windows installer and fixed various issues
  relating to proper operation of zim when compiled as windows executable
* Added option to delete links when deleting a page or placeholder
* Added option to "move" placeholder by updating links
* Fixed bug with interwiki links to other notebooks
* Fixed various bugs due to unicode file names on windows and non-utf8
  filesystems on other platforms
* Fixed bug with non-utf8 unicode in urls
* Fixed bugs with calendar plugin when embedded in side pane
* Fixed support for icons for custom tools
* Fixed bug with indented verbatim blocks (Fabian Stanke)
* Added translation for Traditional Chinese

##  0.46 - Wed 24 Mar 2010
Bug fix release

* Fixed critical bug preventing the creation of new pages.

##  0.45 - Tue 23 Mar 2010
This release adds several new features as well as many bug fixes.

* Added possiblility to add external applications to the menu as "custom tools"
* Added Latex as export format - patch by Johannes Reinhardt
* Improved dependency checks for plugins - patch by Johannes Reinhardt
* Improved application responsiveness by using threading for asynchronous i/o
* Fixed memory leak in the index pane for large notebooks
* Fixed drag-n-drop support for images
* Fixed index, previous and next pages in export templates
* Fixed backlinks in export templates
* Improved fallback for determining mimetype without XDG support
* Added translations for Hebrew, Japanese and Turkish

##  0.44 - Wed 17 Feb 2010
This release adds improved query syntax for search and several bug fixes

* Implemented more advanced search syntax - see manual for details
* Implemented recursive checkbox usage and recursive indenting bullet lists
* Merged "Insert Link" and "Insert External Link" dialogs
* Added options to insert attached images and attach inserted images
* Support for recognizing image attachment on windows
* Fixed bug for lower case drive letters in windows paths
* Fixed bug with non-date links in the calendar namespace
* Fixed bug with invalid page names during move page
* Fixed bugs with unicode in search, find, task list tags, auto-linking pages
  and in url encoding
* Several fixes in behavior of the page index widget
* Added translations for Russian and Swedish

##  0.43 - Sun 17 Jan 2010
This is a bug fix release with fixes for most important issues found in 0.42

* Added update method for data format for older notebooks
* Fixed bug with duplicates showing in the index
* Fixed bug with indexing on first time opening a notebook
* Fixed bug with format toggle buttons in the toolbar
* Fixed bug with permissions for files created by zim
* Fixed bug with selection for remove_link
* Fixed bug with default path for document_root
* Fixed bug with updating links to children of moved pages
* Added strict check for illegal characters in page names
* Improved PageEntry to highlight illegal page names
* Improved user interaction for Edit Link and Insert Link dialogs
* Trigger Find when a page is opened from the Search dialog
* Allow selecting multiple tags in Task List plugin
* Allow negative queries in Task List, like "not @waiting"
* Checkbox icons are now included in export
* Fixed import of simplejson for pyton 2.5 specific
* Translations added for: English (United Kingdom), Greek and Polish

##  0.42 - Sun 10 Jan 2010
This is the first release after a complete re-write of zim in python.
Functionality should be more or less similar to Perl branch version 0.28,
but details may vary.

Additional issues addressed in this release:

* Moving a page also moves sub-pages and attachments
* Deleting a page also deletes sub-pages and attachments
* After deleting a page the user is moved away from that page
* Wrapped lines in bullet lists are indented properly
* Better desktop integration using the default webbrowser and email client
* Added a web-based interface to read zim notebooks
* Task List now supports tags
* Distinguishing between "move page" and "rename page"
* Menu actions like "Rename Page (F2)" now follow the focus and work in the
  side pane as well
* Page title can be updated automatically when moving a page
* "Link" action behaves more like inserting an object instead of applying
  formatting
* File links are now inserted showing only the basename of the file
* Dialogs spawned from another dialog will pop over it
* Dialogs remember their window size
* Allow user to quit individual notebooks even when the tray icon is in effect
* Check for pages that are changed offline now employs MD5 sum to be more robust

Translations available for: Dutch, Estonian, Czech, French, German, Korean,
Ukrainian, Simplified Chinese and Spanish

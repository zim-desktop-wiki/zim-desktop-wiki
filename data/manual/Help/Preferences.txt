Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.4

====== Preferences ======

The preferences dialog  can be accessed with the menu item "//Edit//" -> "//Preferences//". The following options can be configured:

===== Interface =====

**Show controls in the window decoration** determines whether controls are show in the window border. This implies custom window decoration; this may break some platform semantics depending on your operating system. This option requires restart of the application.

**Use <Ctrl><Space> to switch to the side pane** toggles the key binding for <Ctrl><Space>. The reason to toggle this binding 'off' is usually because it is also used for input methods when using non-western scripts.

**Always use last cursor position when opening a page** toggles whether pages are always opened on their last cursor position or not. When this is disabled pages only open with a cursor position when they are opened be a history reference (e.g. the "Back" button or a link from the pathbar).

**Show edit bar along bottom of editor** toggles whether the "Edit Bar" is visible

**Use the <Enter> key to follow links** toggles the key binding to follow links inside a page. If disabled an <Enter> on a link will just be ignored. The <Alt><Enter> key binding can be used as an alternative.

**Show the cursor also for pages that can not be edited** is used to toggle the behavior of the cursor when a page can not be edited. By default, the cursor is not visible when a page is read-only, but keyboard navigation is easier when the cursor is always visible.

**Use custom font** allows selecting a custom font for the editor window. This only applies to the page view itself, the font for all other interface elements is determined by the desktop theme.

===== Editing =====
**Automatically turn "CamelCase" words into links** is used to enable or disable [[Auto Formatting|auto-linking]] CamelCase words.

**Automatically turn wiki page names into links** is used to enable or disable [[Auto Formatting|auto-linking]] words that look like page links, like ``Page:SubPage``, ``+SubPage``, ``:Page`` or ``Page#heading``.

**Automatically turn identifiers starting with "#" into links** is used to enable or disable [[Auto Formatting|auto-linking]] words that look like "anchor links" like ``#heading``.

**Automatically turn interwiki names into links** is used to enable or disable [[Auto Formatting|auto-linking]] words that look like inter-wiki links like ``wp?Topic``.

**Automatically turn file paths into links** is used to enable or disable [[Auto Formatting|auto-linking]] for file paths.

**Automatically select the current word when you apply formatting **is used to enable or disable the feature where pressing e.g. <Ctrl><B> to toggle Bold formatting will automatically select the current word when the cursor is inside a word. The same option also controls whether toggling the format for a heading will select the whole line automatically.

**Unindent on <BackSpace>** toggles the key binding for the <BackSpace> key. If enabled the <BackSpace> key at the start of an indented line will unindent the line, if disabled the will delete the line break instead. The <Shift><Tab> key binding can be used as an alternative.

**Repeated clicking a checkbox cycles through the checkbox states** enables cycling the checkbox state. When turned off clicking a checkbox only toggles the checkbox between it's "checked" and "unchecked" states.

**(Un-)indenting a list item also changes any sub-items** toggles the behavior to make sub-items follow indenting of their parent list item

**Checking a checkbox also changes any sub-items** toggles the behavior to make toggling checkboxes recursive. This feature makes sense for example for todo-lists but not necessarily for other kinds of lists.

If the Reformat wiki markup on the fly option is enabled, zim tries to turn wiki syntax into formatting while you type. For example, typing "''**text**''" will turn into bold formatting when you type a <space> or <enter> after the last "*".

**Default format for copying text to the clipboard** allows you to set the preferred format when you copy some text from zim and paste it in some other application. Default is just plain text, but you can also choose to paste wiki formatted text. This option will only affect copy-pasting if the receiving application asks for simple text input (like a text editor). If it asks otherwise, say HTML input, then zim will paste HTML formatted text automatically.

**Folder with templates for attachment files** is the folder to look for file templates, see [[Attachments]] for details.

===== Plugins =====
This tab allows you to enable or disable the various [[Plugins]]. Selecting a plugin will show a short description, select "More" to open the relevant manual page in this manual for a specific plugin or select "Configure" to set plugin specific preferences.

===== Applications =====

Changing default applications does just set the defaults for Zim. If you are on a unix/linux based system that uses the XDG configuration system, this likely will change your system defaults as well. These options are offered here for convenience in case your system uses a different configuration system.

**Set default text editor** sets the text editor that opens when e.g. the "Edit Source" menu option is used.

**Set default browser** allows changing the default browser used to open both local HTML files and remote "http://" and "https://" links. If you want another browser for those links, use the "open with" context menu, which will allow setting defaults per URL scheme.

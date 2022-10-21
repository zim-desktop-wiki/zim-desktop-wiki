Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.4
Creation-Date: 2022-04-24T00:00:00+03:00

====== Window Title Editor ======

This plugin allows editing the window title.

**Dependencies:** This plugin has no additional dependencies.

===== Title template =====

You can choose between the following ready-made templates:

* **Page Path - Notebook Name**, eg. "''Projects:CustomerA:MyProject - WorkNotebook''" (newer Zim default)
* **Notebook Name - Zim**, eg. "''WorkNotebook - Zim''" (older Zim default)
* **Page Name — Page Title — Zim**, eg. "''MyProject — My Project's First Heading — Zim''" (inspired by the Python docs)
* **Notebook Name: Page Title (Page Source Path)**, eg. "''WorkNotebook: My Project's First Heading (/home/me/Notebooks/WorkNotebook/Projects/CustomerA/MyProject)''" (//it's free real estate!//)
* **Custom:** [[Plugins:WindowTitleEditor#template-string-for-custom-format|see intructions below]].

===== Template string for custom format =====

The custom format string is used as a Python [[https://docs.python.org/3/library/string.html|string.Template]]. Placeholders are substituted as follows:

* ''$path'' → page path, eg. ''DesktopInvasion:ZimWiki''
* ''$page'' → page name, eg. ''ZimWiki''
* ''$title'' → page title/first heading, eg. ''Zim Desktop Wiki''
* ''$source'' → page source, eg. ''/path/to/ConquestPlans/DesktopInvasion/ZimWiki.txt''
* ''$notebook'' → notebook name, eg. ''ConquestPlans''
* ''$folder'' → path to notebook root, eg. ''/path/to/ConquestPlans''
* ''$ro'' → " ''[readonly]'' " if the page or notebook is readonly, otherwise "" (empty string). Will be appended to the end of the title, if not present in the template.
* ''$'' → ''$'', ''$$'' → ''$'', ''$any'' → ''$any''; ie, no errors will be thrown
* ''Zim'' → ''Zim'', other text shows up as-is

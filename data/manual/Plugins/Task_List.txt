Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.6

====== Task List ======

The Task List plugin adds a dialog that lists open items across all pages of the current notebook. In a way, it is a specialized search function. An open item or task is defined by a single line and can have tags and a priority.

**Dependencies:** This plugin has no additional dependencies.

**See also:** This manual page documents the options of the plugin and how the plugin interpretes tasks. For more background information on how and when to use it see:  [[Usage:ToDo Lists]] and [[Usage:Getting Things Done]]. This plugin is often used in combination with the [[Journal]] plugin.


===== Preferences =====
The option **Show tasklist button in headerbar** determines whether a button is shown in the headerbar on the top of the window for opening the tasklist dialog.

The option **Show "GTD-style" inbox & next actions lists** determines what lists are shown in the selection pane. See details below.

The options **Show tasklist in sidepane** and **Position in the window** allow you to embed the tasklist in one of the side panes of the window. **Show due date in sidepane**, **Show start date in sidepane** & **Show page column in the sidepane** determine which columns are shown in the side pane.


===== Notebook properties =====
If the option "**Consider all checkboxes as tasks**" is enabled any checkboxes found will appear in the task list. If it is disabled only checkboxes that have a task label (like "FIXME" or "TODO") will appear in the list.

The option **Labels marking tasks** gives a comma-separated list of labels that are used to flag tasks. By default, these are "TODO" and "FIXME" but this can be customized.

The option **Labels for "waiting" tasks** gives specific labels for tasks that are waiting for something and thus are not immediately actionable, typical usage is tasks that are delegated or planned already.
The option **Tags for "waiting" tasks** has the same meaning, but uses tags rather than labels to flag tasks.

If **Use date from journal pages** is enabled, tasks found in pages that belong to the [[Journal|Journal plugin]] will get that calendar date as starting date and/or due date. If the page covers multiple days (e.g. a weekly page) the last day of the period will be taken as the due date while for the start day the first day will be used. If the page covers a week or a month and the task appears under a heading which gives the specific day, the task will be assigned to that day. For this to work, the heading must contain an explicit anchor id which gives the date in the standard date format (see the default Journal template for an example how to generate those).

The options **Section(s) to index** and **Section(s) to ignore** can be used to limit the namespaces that are indexed for tasks. By default, the whole notebook is used, but if either or both of these options are used, only the specified set of sections is indexed. Multiple namespaces can be given separated by a "'',''".

If the option **Show page names in selection pane** is enabled, it will add the page name elements of the page where the task is found in the selection pane.

If the option **Don't count Saturday and Sunday as working days** is enabled the remaining days before a task is due are counted based on a 5 day workweek (Monday - Friday).


===== Selection =====
The selection pane has several categories for selection: **Lists**, **Labels**, **Tags** and **Page**.

* Lists: The default lists are described below
* Labels: These are labels like "TODO" or "FIXME" that can occur at the start of a task description. The exact labels can be configured with the **Labels marking tasks** preference. If you select multiple labels, tasks with any of the selected labels will be shown ("or" selections)
* Tags: These are "@name" tags that occur in the task description. If you select multiple tags, tasks will be shown that match all selected tags ("and" selection)
* Page: These are unique parts of a page name, which allows to use the page path in a tag-like way. If you select multiple pages, tasks of any of the selected pages will be shown ("or" selection)


==== Lists ====
In the selection pane there are 3 "lists": **All tasks**, **Active** and **Waiting**:

* All tasks: this is an overview of all tasks, it is represented as a tree with parent and child tasks
* Active: this list shows all open tasks that have no child items, do not have a start date in the future and are not waiting, it is a flat list of all items that can be consdered "actionable"
* Waiting: this list shows all tasks that have been labelled as "waiting" with the label configured by the **Labels for "waiting" tasks** property

When the preference **Show "GTD-style" inbox & next actions lists** is enabled the Active list is subdivided in 3 sub-lists:

* Inbox: this list shows a subset of active tasks that are "unclassified" - this means they do not belong to a project and have no prio or due date set. Also it hides items that have closed child tasks, which will show up in the "projects" list
* Next Actions: like the "active" list but it only shows tasks that have either a prio or a due set or are part of a project, this distinguises these items from "inbox" items. Also it hides items that have closed child tasks, which will show up in the "projects" list
* Projects: this list shows all open tasks that have child tasks (open or closed)

With these 3 lists one can work with a "GTD like" approach. To create an inbox item you just write down a task anywhere in a page without adding prio or due date (tags are allowed). When you are in review mode, you classify these tasks, add child tasks etc. and they move to either the "Next actions" or the "Projects" list automatically. Similarly in review mode you can go over the projects and find where to add more child tasks.

==== Labels ====
Labels like "TODO" or "FIXME" can occur at the start of a task description. The exact labels can be configured with the **Labels marking tasks** preference. The selection pane allows selecting specific labels because typically when multiple labels are used, they are represent different categories of tasks.

==== Tags ====
Another way to select sets of tasks is by using tags. A typical way to use these is to give context to when or where a task is relevant. E.g. tasks can be labelled @home or @work or you might label tasks by the person you need to talk to - that way you can draw up a quick lists of things to discuss in the next meeting.

Tags are inherited by sub-tasks. Therefore selection by tag also includes tasks that may not have the tag directly. The reason is that sub-tasks are expected to have the same context as their parent task.

==== Page selection ====
In the selection page the unique parts of a page name are shown if the option **Show page names in selection pane** is enabled. This allows to use the page path in a tag-like way.

It allows selecting all tasks that share a common parent page. E.g. if you have a notebook section "Projects" selecting the "Projects" label in the page selection will show all tasks that are on a sub-page of the "Projects" section. And similar you can select all tasks in the "Journal" section.

It also allows to combine tasks from different pages that have a common name. E.g. if you organize your tasks per customer and you have pages "Customer A:Brainstorm" and "Customer B:Brainstorm" selecting the "Brainstorm" label in the page selecting will show alls tasks on both pages combined.

If you want to show tasks of one specific page only, the page selection may not be what you want. In that case you can just type the full page name in the entry for filtering tasks. This works because the filter also takes into account the "page" column of the task view.

===== Usage =====

==== Using Checkboxes ====
The first way to use the task list is to define open items by checkboxes. A list like this will be interpreted as a task list and each individual line will appear in the task list dialog.

	[ ] Buy rice @groceries
	[ ] Call Susan to invite for diner <2017-05-01 !
	[ ] Print menu @desk

In this example the second item will have the highest **priority** because of the "!", the more exclamation marks the higher the priority. Also, the words with an "@" will be considered **tags**, so the dialog will show the tags "groceries" and "desk" which can be used for filtering the task list.

A **due date** is prefixed by a "<": you must complete the task **before** that date.
A **start date** is prefixed with ">": you should start the task **after** that date.

	[ ] Tasks due 27 March 2017 <2017-03-27
	[ ] Task that will only start in a few years (as of writing) >2020-01
	[ ] Dates can also be given by weeknumber <17W13

The following date forms are supported:
* Day by date using: ''yyyy-mm-dd''  for example 2017-02-16
* Month using: ''yyyy-mm'' for example 2017-02
* Week using: ''(yy)yyWww'' or ''(yy)yy-Www'', for example 2017W07, 17W07 or 17-W07
* Day by week using  week notation followed by ''-D'' where "D" is the number of the day in the week; for example 17-W07-2 for Tuesday
* Week and day by week notation can also use ''Wkyyww(.D)'' for example wk1707 and wk1702.2

To avoid confusion between mm/dd, dd/mm and yy-mm notations neither of these is supported and the year should always be given in 4 digits for dates. For week notation a two-digit year is supported; these are always prefixed by "20", so "01W17" becomes 2001W17 and "99W05" becomes 2099W05. For years starting with 19 (or any other century) the full four-digit year needs to be used.

Week numbers follow the iso calendar. However, depending on locale Sunday can either be the first day of the starting week or the last day of the ending week. In the weekday notation, this is made explicit by using "0" for Sunday at the start of the week and "7" for Sunday at the end of the week. Thus the dates "W1707.7" and "W1708.0" are the same day.

For backward compatibility with previous versions a due date can also be given between square brackets like "''[d: yyyy-mm-dd]''". This form also supported more ambiguous formats, e.g. "''dd/mm''". Using this form is no longer recommended, it is better to use the unambiguous forms described above.

A task in a checkbox list can also have sub-items. This can help split up a complex task into step by step action items. For example:

	[ ] Organize party <2017-08-19 !
		[ ] Send invitations by first of month <2017-08 !!
		[ ] Cleanup living room
			[ ] Get rid of moving boxes <2017-08-10
			[ ] Buy vacuum cleaner <2017-08-15
		[ ] Buy food & drinks

Such sub-items will also show up in the tasklist as sub-items below the main task in a hierarchical tree. Note that sub-items that do not have an explicit due date or priority will inherit these from the main task. In this example, "//cleanup living room//" and "//buy food & drinks//" items inherit the due date and priority from the main task. "//send invitations//" will have an earlier due date and a higher priority because they are explicitly specified.

In this example the "Active tasks" list will show only 4 items: "Send invitations", "Git rid of moving boxes", "Buy vacuum cleaner" and "Buy food & drinks". These 4 represent the lowest level "next steps" that can be acted upon. When you close the tasks "get rid of moving boxes" and "buy vacuum cleaner" the "cleanup living room" becomes active. This should prompt you to either do it and close it, or detail our further sub-tasks.


==== Using labels ====
The second way to use the task list is by using labels like "TODO" or "FIXME" in your notes. Labels can appear at the start of a line or directly after a checkbox. The rest of the lines are parsed the same as a task description after a checkbox. So the following will also be considered a task:

	FIXME: finish the previous paragraph

Different labels can be used similar to tags to distinguish different categories of tasks.

As a special case labels can be used to flag a whole list being a task list. In that case, the tag needs to start a new paragraph and be on a line by itself before the first checkbox. This usage is especially useful when the option "Consider all checkboxes as tasks" is turned off. Any tags on this first line will be applied to the whole list. However, no other words should appear as that would make this first line a regular item and cause the list to be ignored. An example of this usage is as follows:

	TODO: @home
	[ ] Call Susan to invite for diner <2017-05-01 !
	[ ] Print menu @desk

Now both items will get the tag "@home" appended.

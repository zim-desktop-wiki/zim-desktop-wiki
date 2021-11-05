Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.6
Creation-Date: Wed, 08 Jul 2009 20:27:21 +0200

====== Getting Things Done ======

The **GTD** methodology is a specific system for maintaining [[ToDo Lists]]. It is coined in the like named book by David Allen. It's main philosophy is that you need to capture **all** loose ends on a list in order to give you peace of mind because you do not have to keep them in your head all the time. This only works if you are diciplined in reviewing your lists and have them accessible so you always know what the next thing is that you can do given the time and tools available at a certain moment.

For those not familiar with the book either read it or check any of the numerous websites discussing it or the [[https://en.wikipedia.org/wiki/Getting_Things_Done|Wikipedia article]].

As the book only describes the methodology it leaves room to the user how to implement it and what tools to use. You can do it using some software task manager but also just using paper and pencil. There are many software tools designed specifically for the GTD workflow, but zim is not one of them. However the advantage of using a more generic editor like zim is that it is easier to adapt to how you want to do things. The downside can be that you need a bit more discipline compared to using a tool that enforces the GTD way of working. 

===== Workflow =====
The basic workflow consists of the following steps:
* Collect - write down all "open loops" and loose end - make a full brain dump
* Clarify - for each item clarify whether it is actionable and if so what is the intended outcome
* Organize - make sure actions end up on the right list
* Reflect - review the lists and make sure they are up to date
* Do - now you have clear what to do, do it !

For clarifying and organizing, the book advises a flowchart which looks more or less like this:

	{{../GTD_flowchart.png}}


===== Using the Tasklist plugin for GTD =====
The [[Plugins:Task List|Task List plugin]] can be used to track open actions across the pages of a notebook. This makes it easy to organize actions by context even if they are not written down all on the same page. You can create actions anywhere by using checkboxes and use the plugin to see an overview.

The plugin has a specific preference for showing GTD style lists for "Inbox", "Next actions" and "Projects". See the plugin documentation for more details.

Be aware that not all lists need to be [[Help:Check Boxes|checkbox lists]] that show up in the tasklist. For example, if you have regular meetings with specific people, you could just have a separate page for these and add new items to discuss on the top. At the meeting you open the page to write down the minutes and check the items you want to discuss. No need to have these show up in your "next actions" list.

Similarly all kind of "tickler" lists can maintained in separate pages without making them actions. As long as you review them on a regular basis. Examples could be pages like "Borrowed items" "Books to read" etc. etc. No need to have these show up in your next actions lists unless there is something to do on the short time like "bring back ... to ... before ..." or "buy ... @bookstore". 

===== Using the Journal plugin for GTD =====
Although the GTD system does not really use a journal - just a calendar - a daily journal can very well be used to capture tasks. One way of working is to use a weekly journal to capture tasks that pop up during the week and that do not belong to any specific projects. The [[Plugins:Journal]] plugin can be used to setup a notebook section with daily or weekly pages. You might also to start the habit of doing a weekly review and check all open tasks from the past week. See also the page on how to use zim for a [[Daily Journal]].

===== How to organize a Zim notebook for GTD =====
To organize a notebook for running a GTD style system, you may consider creating the following pages or sections:

* "Inbox" / "Home" page — page to capture quick notes / ideas / tasks without need to think where they go in the end
* "ToDo" / "Actions" — list of actions that you want to track, but do not belong to a project
* "Projects" section — notebook section with one page per project for larger & longer running projects, would also include reference material per project
* "SomeDay" / "Maybe" section — like the projects section, but for projects that are not yet started
* "Notes" / "Reference" — topic based pages that are not projects, loose reference materials
* "Review" — page or section with reminders of things you need to check during weekly review ("tickler file")
* "Archive" — section to store project or reference pages for topics that are no longer active

Tasks can be defined anywhere in the notebook and managed with the tasklist plugin, but open tasks should normally only be found in the "Inbox" and "Projects" pages. The tasklist plugin can be configured to ignore sections like "SomeDay" or "Archive" in case there are still open tasks there.

You can setup the "**Inbox**" page as the home page of the notebook (see [[Help:Properties|properties]]) to have a quick link to it with ''<Alt><Home>'' or using the "home" button in the toolbar. You can also use the [[Plugins:Quick Note|Quick Note plugin]] to capture stuff here.

The "**ToDo**" page contains actions that are clarified and no longer belong in the Inbox but also do not belong to a specific project. An alternative is to use a journal page for this and track these e.g. per week. In that style, the journal might also double as an Inbox but both can be used as well.

The "**Projects**" section is reserved for larger projects that need there own page or even a whole sub-section including their own reference material or e.g. a record of meetings. If you want to keep overview of projects that are started and projects that are still "incubating" a "**SomeDay**" section can be used to park future projects.

The "**Notes**" section can be used to store all material that you may need to do your work, but is not related to a particular project.

The "**Review**" page can be used to keep bullet lists (not action lists) of things that are not actionable (yet) but need to be checked during your weekly review. This may include re-curring chores that you might need to plan or attention areas. This is sometime also referred to as a "tickler file". This can actually be a section with sub-pages if you keep multiple of these lists.

===== What is a "Project" ? =====
When talking about "projects" there can be some confusion. In a business context people think about projects as part of the formal organization of the company with their own budget, project lead etc. At home a "project" is usually something big like a renovation or other DIY undertaking. However in the GTD context a project is any activity that can be split in multiple actions. So even relative small planning activities generate a "project". For example finishing a document may require setting up a few meetings and requesting specific information apart from the actual writing and thus becomes a "project".

In a Zim notebook you can track projects with their own page or notebook section, but this is only needed for "large" projects that also generate a lot of notes and attachment. A small project of just a few tasks can be represented as a checkbox list with a parent tasks (the "project") and sub-tasks (the actions).

It helps to think of projects as outcomes or responsibilities with the actions reflecting steps to take towards the outcome. If an action does not have a verb changes are it is really a project.

===== How to do the weekly review =====
For the weekly review you just need to go over all relevant lists. The hard part is to set apart time and be disciplined in doing this.

The lists to consider:
* All of the lists in the tasklist plugin
* The lists in the "Review" section of the notebook
* The list of projects in the "Projects" and "SomeDay" sections




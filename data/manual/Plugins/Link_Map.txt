Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.4
Creation-Date: Fri, 13 Mar 2009 22:49:34 +0100

====== Link Map ======

Having a graph of linking relations allows an alternative view of the internal organization of a notebook. The use of this depends on your use of links. If you hardly use any links, the hierarchic index probably contains all the organization you do. But if you use links extensively there is a deeper structure than the one-dimensional index.

For example, in a notebook with notes on specific topics, this link map shows the "landscape" around a specific subject by showing all pages linking to it. Because link relations are shown for a number of steps away from the current page, you'll immediately notice if all pages linking here also all link to another page etc.

Another example is applying tags by linking pages to a special tag page or to a category page. Now the link map shows this link and also shows other pages linking to that tag as well as other tags where those pages are linking. Again, any oddities in the graph will stand out visually.

Obvious future improvement would be to have a page "type" and apply different colors / shapes in the graph based on that. E.g. make a category page a different color from a normal page.

Another future improvement would be the ability to directly add nodes to the link map. This would allow the map to be used in the style of a "mind map" basically drawing a graph of related nodes and then, per node fill in any extra information in the page for that node.

**Dependencies:** This plugin requires GraphViz to be installed as well as the "xdot" program.

===== Options =====

The option **Show linkmap button in headerbar** determines whether a button to show the linkmap dialog is shown in the headerbar on top of the window.

The option **Autozoom to fit map** determines whether the map gets automatically zoomed out to fit inside the window.

The option **Follow main window** determines whether refreshing the map rebuilds the currently shown view or builds a graph for the page that's open in the main window. When set, the map is also updated when opening a map link in the main window.

The option **Always open links in new windows** does what the name implies. You can middle-click to open links in new windows regardless.

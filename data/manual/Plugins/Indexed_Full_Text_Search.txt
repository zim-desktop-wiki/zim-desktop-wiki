Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.6
Creation-Date: 2023-10-11T16:52:26+02:00

====== Indexed Full Text Search ======

This plugin allows to massively speed up the search in page contents, by up to 95%. Simply enable the plugin. The index will be automatically recreated, after which the faster full-text search will be available.

This is achieved by caching a reverse index of tokens (i.e. words) in the index using ''sqlite''. For that to work, it requires a version of ''sqlite'' with the FTS5 extension. This new index will be around 5x bigger than before (for a 1500-page notebook with around 500 words per page, the index grows from 1.7 MiB to about 5.5 MiB).

===== Options =====
The option **Remove diacricitcs before indexing** alters the indexer such that for example "Apfel" and "Äpfel" are both indexed as "Apfel", and "avião" will be indexed as "aviao". This means searching for "apfel" will then return both pages with matches for "Apfel" and for "Äpfel". While this may be desireable for some use cases, it is turned off by default to more closely resemble the search functionality without this plugin.
Note that currently, if "Remove diacritics before indexing" is set to true, in the example above, searching for "Äpfel" will not return any results due to implementation shortcomings of the full-text search module.

The option **Additional token characters** can be used to set additional characters which will be considered part of a word (a "token"). Adding "-", for example, will lead to words such as "lorem-ipsum" being added to the index entirely, so they can be searched for using "lorem-ipsum" as a search string but not "lorem ipsum".

After changing these options, the index of each notebook must be re-generated.

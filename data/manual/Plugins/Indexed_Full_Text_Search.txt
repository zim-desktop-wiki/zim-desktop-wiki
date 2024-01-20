Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.6
Creation-Date: 2023-10-11T16:52:26+02:00

====== Indexed Full Text Search ======

This plugin allows to massively speed up the search in page contents, by up to 95%. Simply enable the plugin. The index will be automatically recreated, after which the faster full-text search will be available.

This is achieved by caching a reverse index of tokens (i.e. words) in the index using ''sqlite''. For that to work, it requires a version of ''sqlite'' with the FTS5 extension. This new index will be around 5x bigger than before (for a 1500-page notebook with around 500 words per page, the index grows from 1.7 MiB to about 5.5 MiB).

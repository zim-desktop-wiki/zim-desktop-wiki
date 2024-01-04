Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.4
Creation-Date: 2013-04-14T12:14:49+02:00

====== Commandline Options ======

**Output from "zim --help":**

'''
usage: zim [OPTIONS] [NOTEBOOK [PAGE_LINK]]
   or: zim --gui [OPTIONS] [NOTEBOOK [PAGE_LINK]]
   or: zim --server [OPTIONS] [NOTEBOOK]
   or: zim --export [OPTIONS] NOTEBOOK [PAGE]
   or: zim --import [OPTIONS] NOTEBOOK PAGE FILES
   or: zim --search NOTEBOOK QUERY
   or: zim --index  [OPTIONS] NOTEBOOK
   or: zim --plugin PLUGIN [ARGUMENTS]
   or: zim --manual [OPTIONS] [PAGE_LINK]
   or: zim --help

NOTEBOOK can be a local file path, a local file URI or a notebook name
PAGE is be a fully specified page name
PAGE_LINK is a fully specified page name optionally extended with an anchor ID

General Options:
  --gui            run the editor (this is the default)
  --server         run the web server
  --export         export to a different format
  --import         import one or more files into a notebook
  --search         run a search query on a notebook
  --index          build an index for a notebook
  --plugin         call a specific plugin function
  --manual         open the user manual
  -V, --verbose    print information to terminal
  -D, --debug      print debug messages
  -v, --version    print version and exit
  -h, --help       print this text

GUI Options:
  --list           show the list with notebooks instead of
                   opening the default notebook
  --geometry       window size and position as WxH+X+Y
  --fullscreen     start in fullscreen mode
  --standalone     start a single instance, no background process

Server Options:
  --port           port to use (defaults to 8080)
  --template       name or filepath of the template to use
  --private        serve only to localhost
  --gui            run the gui wrapper for the server

Export Options:
  -o, --output     output directory (mandatory option)
  --format         format to use (defaults to 'html')
  --template       name or filepath of the template to use
  --root-url       url to use for the document root
  --index-page     index page name
  -r, --recursive  when exporting a page, also export sub-pages
  -s, --singlefile export all pages to a single output file
  -O, --overwrite  force overwriting existing file(s)

Import Options:
  --format         format to read (defaults to 'wiki')
  --assubpage      import files as sub-pages of PATH, this is implicit true
                   when PATH ends with a ":" or when multiple files are given

Search Options:
  None

Index Options:
  -f, --flush      flush the index first and force re-building

Try 'zim --manual' for more help.
'''


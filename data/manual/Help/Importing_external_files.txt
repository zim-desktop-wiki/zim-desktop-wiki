Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.6
Creation-Date: 2010-04-03T23:35:33.816582

====== Importing External Files ======


There is a dialog to import a text file into the notebook as a page. See the menu item //Files// -> //Import page...//

If you want to import multiple files you can either use the ''zim --import'' commandline option or format the files yourself and move them to the right location.


===== Import by commandline =====

The commandline option ''zim --import'' can be used to import multiple files into an existing notebook. See [[Commandline Options]] for options to this command. You can either import a single file to a given page name or multiple files as sub-pages of a given page.

If you want to create a new notebook from imported files, first create an empty notebook and then import the files.

The import command will never overwrite existing files. If pages by the same name already exist a number will be post-fixed.

Note that rebuilding the index may take quite some time if you have added many pages.
If indexing does not trigger automatically you can use the //Tools// -> //Re-build Index// menu item.


===== Import by moving files =====

==== Pages in Zim ====
Pages in Zim are stored as text files in normal folders and subfolders in your file system.
The file name is used as the page name. The hierarchical structure is similar to the one appearing in the index. The file names should contain **no blanks**; instead use underlines. So a filename can look like this: "Help_on_creating_notebooks.txt" or "HelpOnCreatingNotebooks.txt".

Important: The content of the text file must be UTF-8 or ASCII encoded.  If you are not familiar with character encoding, please read https://en.wikipedia.org/wiki/Character_encoding. If files contain different encoding and zim tries to read them as UTF-8 an error will occur.

Some word processors allow checking the encoding, e.g. with the small editor Mousepad load the file, then click Save as, then the button on the bottom right just above the save button should show UTF-8. If not and if you cannot save with this configuration Zim will not work. You can also use the Geany editor for the same purposes.

The filename should be encoded in the proper encoding for your file system. You can easily check this by making sure your operating system default file browser shows the file names correctly. There are a number of characters that are forbidden in page names, these are: "?", "#", "/", "\\", "*", '"', "<", ">", "|" and "%". These are forbidden because they have a special meaning in the zim wiki syntax or because they can not be encoded on common file systems.

Finally zim pages that have a ".txt" extension must start with a header line that identifies the content as zim wiki formatted text, optionally followed by more header lines and separated from the main content by an empty line. Like this:

	''Content-Type: text/x-zim-wiki''

	''=== First heading ===''
	''some text''

Without the heading line, ".txt" files are regarded as text file attachments.


==== Moving pages into an existing notebook ====
If you have files that conform with the page file format as description above, you can import them as follows

* Close  Zim
* Move these files to the desired location in the notebook folder
* Reopen the notebook in Zim and the new pages should appear in the index

Note that rebuilding the index may take quite some time if you have added many pages.
If indexing does not trigger automatically you can use the //Tools// -> //Re-build Index// menu item.


===== Creating a new Notebook =====
If you wish to create a new notebook, e.g. from data from another application that allows exporting its content as text files, you can create a new notebook folder and move the files in as described above.

Now open zim and go to the menu item //File// -> //Open Another Notebook...// In the dialog that appears you can add a new notebook and specify the folder you just created. You will get a warning that the folder is not empty, but this can be ignored in this case. Now you can open the newly added notebook from the dialog.

The notebook that opens should show pages corresponding to the file structure you created in the folder.

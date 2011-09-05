/* -------------------------------------------------------------------

start_zim_portable.js

Because Zim doesn't currently support storing Notebook paths relative
to $HOME or any other environment variable, and because Windows may
map a removable storage device to a different drive letter each time,
it is necessary to erase the old notebooks.list and rewrite it each
time we start Zim Desktop Wiki Portable.

This script will do the following:

* Search for all notebooks in ./Data/Notebooks and add them to a fresh
  ./Data/Config/zim/notebooks.list .

* If a notebook folder called $DEFAULT_NOTEBOOK_NAME is found, it will
  be listed in notebooks.list as the default notebook; otherwise there
  will be no default.

------------------------------------------------------------------- */


/* -------------------------------------------------------------------
Edit the default notebook's folder name here. If this folder name is
not found in ./Data/Notebooks, the resulting notebooks.list will have
no default notebook, and the user will be prompted for which notebook
to open.
------------------------------------------------------------------- */
DEFAULT_NOTEBOOK_NAME = "Default";


/* -------------------------------------------------------------------
Do not change anything below this line.
------------------------------------------------------------------- */

fso = WScript.CreateObject("Scripting.FileSystemObject");
paths = {};

/** Main function */
function main() {
	setupPaths();
	var cat = getNotebooksCatalog();
	writeNotebooksList(cat);
}

/** Set global path hashmap and create some paths if they don't exist */
function setupPaths() {
	paths.root = fso.Getfile(WScript.ScriptFullName).ParentFolder.ParentFolder.ParentFolder;
	paths.data = fso.BuildPath(paths.root, "Data");
	paths.notebooks = fso.BuildPath(paths.data, "Notebooks");
	paths.config = fso.BuildPath(paths.data, "Config");
	paths.configzim = fso.BuildPath(paths.config, "zim");

	var list = [
		paths.data,
		paths.notebooks,
		paths.config,
		paths.configzim
	];
	for(var i = 0; i < list.length; i++) {
		if(!fso.FolderExists(list[i])) {
			fso.CreateFolder(list[i]);
		}
	}
}

/** Change a file path to a file:// URI */
function makeUri(path) {
	return "file:///" + path.replace(/\\/g, "/");
}

/** Search for notebooks in paths.notebooks and return a struct of
    {def, list} where def is the URI of the default notebook and list
    is a list of notebook structs */
function getNotebooksCatalog() {
	var booksEnum = new Enumerator(fso.GetFolder(paths.notebooks).SubFolders);
	var r = {};
	r.def = "";
	r.list = [];
	for(; !booksEnum.atEnd(); booksEnum.moveNext()) {
		var folder = booksEnum.item();
		var notebook = {};
		notebook.uri = makeUri(folder.Path);
		notebook.name = folder.Name;
		notebook.interwiki = "None";
		notebook.icon = "None";
		r.list.push(notebook);
		if(notebook.name.toLowerCase() == DEFAULT_NOTEBOOK_NAME.toLowerCase()) {
			r.def = notebook.uri;
		}
	}
	return r;
}

/** Write a list of notebooks to ./Data/Config/zim/notebooks.list */
function writeNotebooksList(catalog) {
	var out = fso.CreateTextFile(fso.BuildPath(paths.configzim, "notebooks.list"), true);
	var i;
	var item;
	out.WriteLine("[NotebookList]");
	if(catalog.def) {
		out.WriteLine("Default=" + catalog.def);
	} else {
		out.WriteLine("Default=");
	}
	for(i = 0; i < catalog.list.length; i++) {
		out.WriteLine(catalog.list[i].uri);
	}
	out.WriteLine("");
	for(i = 0; i < catalog.list.length; i++) {
		item = catalog.list[i];
		out.WriteLine("[Notebook]");
		out.WriteLine("uri=" + item.uri);
		out.WriteLine("name=" + item.name);
		out.WriteLine("interwiki=" + item.interwiki);
		out.WriteLine("icon=" + item.icon);
		out.WriteLine("");
	}
	out.Close();
}

main();

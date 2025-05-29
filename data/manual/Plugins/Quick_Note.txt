Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.4
Creation-Date: 2010-04-24T13:49:51.331910

====== Quick Note ======
The "Quick Note" plugin offers a dialog for inserting quick notes into a notebook. It can be invoked from the commandline and can therefore easily be bound to keyboard shortcuts or used in scripts.

**Dependencies:** This plugin has no additional dependencies.

**Commandline: **''zim'' --plugin quicknote [OPTIONS]

**Options:**

'''
--notebook URI         Select the notebook in the dialog
--page STRING          Fill in full page name
--section STRING       Fill in the page section in the dialog
--basename STRING      Fill in the page name in the dialog
--append [true|false]  Set whether to append or create new page
--text TEXT            Provide the text directly
--input stdin          Provide the text on stdin
--input clipboard      Take the text from the clipboard
--encoding base64      Text is encoded in base64
--encoding url         Text is url encoded (In both cases expects UTF-8 after decoding)
--attachments FOLDER   Import all files in FOLDER as attachments, wiki input can refer these files relatively
--option url=STRING    Set template parameter
'''

===== Template =====
The plugin uses a template for the note text. The following template parameters are supported

* ''text'' this is replaced by the input text (either from the ''--text'' argument, clipboard or stdin input
* ''place_cursor()'' the method results in the cursor being placed at that location in the dialog

In addition any '''--option'' key-value pair that is given on the commandline will be available to the template as a field. The default example is to provide an url for the source of the note. Which will be filled in in the template for the ''url'' field.

See [[Help:Templates]] for standard methods availble in templates, like ''strftime''

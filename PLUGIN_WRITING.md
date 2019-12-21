Plugins
=======

Plugins are one of the two extension mechanisms supported by zim. Plugins are loaded
as part of the application code and can modify key components of the interface.
In fact one of our design goals is to keep the core functionality limited and
ship default plugins for anything a user would want to be able to disable.

( The other extension mechanism being "custom tools". The later allows defining
tools in the zim menu that call an external script or application. This can be
used to add some simple functions that only act on the files in the notebook. )

Plugins are written in Python3 and consists of a class defining the plugin and
one or more extension classes.

See the module `zim.plugins` for API documentation of the plugin framework.

**NOTE:** Under the GPL license used for distributing this program all plugins
should also be licensed under the GPL. A closed source plugin extension is not
allowed. A plugin is allowed to call any non-GPL program as long as the plugin
itself is under GPL and the non-GPL program runs as a separate process with a
clearly defined inter process communication interface.


## Defining your plugin
Plugins are simply sub-modules of the `zim.plugins` python package. However
only core plugins should be placed directly in the module folder.

To allow plugins to be installed locally, the `$XDG_DATA_HOME/zim/plugins`
folder and all `$XDG_DATA_DIRS/zim/plugins` folders are added to the search
path for `zim.plugins`.

By default the home folder would be `~/.local/share/zim/plugins`.

The best for packaging is then is to organize your plugin as a folder with a
`__init__.py` containing the main plugin class. Users can then directly unpack
this folder to `~/.local/share/zim/plugins` or directly branch you git
repository to this location.

The main plugin class should provide information for Zim to recognize the plugin
and add it to the preferences dialog.

Example plugin class:

```python3
  from zim.plugins import PluginClass

  class MyPlugin(PluginClass):

    plugin_info = {
      'name': _('My Plugin'),
      'description': _('My first plugin')
      'author': 'Your Name',
    }
```

**NOTE:** when testing your plugin you will have to quite zim and restart after
changing the plugin code because once a plugin is loaded it keeps using the copy
from memory.

## Adding functionality to your plugin

The plugin class itself does not do much other than providing information about
the plugin and it's preferences.

To add functionality to your plugin you need to define one or more classes that
do the actual work. These will be "extension" classes and must derive from a
extension base-class.

You can find all extension points in the application by searching for the
`@extendable` class decorator. Classes that are extendable have this decorator
and thus declare what extension base class they support.

For example to add functionality to the `PageView` class, you must define a
class derived from `PageViewExtension`.

At the time of writing these extension base-classes are defined:
  - `NotebookExtension`: for functions that act on signals of the notebook
  - `PageViewExtension`: for functions that add functionality to the editor
    window, or want to add side panes next to the editor
  - `InsertedObjectTypeExtension`: special extension for plugins that want to
    define an object type (e.g. equation) that can be rendered in line in the
    text -- see also to `zim.plugins.base.imagegenerator` module
  - `MainWindowExtension`: for any other changes to the mainwindow that are not
    handled by a `PageViewExtension`

When you define a subclass of such an extension class it will be loaded
automatically by the plugin for each instance of the target component.

Key interfaces for extensions are: adding actions, adding widgets, connecting
to signals and calling methods on the extended object.

Apart from extensions there is one other class that will also be used
automatically: Classes derived from the `Command` class are used to handle
commandline arguments in the form "`zim --plugin yourplugin`".


## Preferences and properties

Preferences are maintained by the plugin object and are global for the
application. That means that they apply in the same way for all notebooks.
If your plugin has behavior that should be different per notebook you need to
use the notebook properties instead.

Preferences can be defined by adding a list of `plugin_preferences` to your
plugin class. Within the plugin these are accessible through the `preferences`
dict and in the user interface they will show up in the plugin configuration
in the preferences dialog.

Notebook properties can be defined similarly by adding a list of
`plugin_notebook_properties` to the plugin class. To obtain the properties
for a specific notebook as a dict you need to call the plugin method
`notebook_properties()`. In the user interface they will show up in the
properties dialog.

## Actions

Some extension classes use actions to define menu items. These can be defined
using the `@action` or `@toggle_action` decorators from the `zim.actions`
module.

## Accessing functions of other plugins

The functions `zim.plugins.find_extension()` and `find_action()` can be used to access
extensions and actions defined by other plugins.


## Signals

Zim is build using the Gtk / GObject toolkit. This toolkit relies heavily on
the concept of "signals" to collaborate between classes.

In short this means that any class can define a number of signals that are
emitted for various events. Objects that are interested in these events can
register an event handler using the `connect()` method.

Zim defines a `SignalConnectorMixin` class in `zim.signals` with some
convenience methods for classes that want to connect to signals.

For classes that do not derive for GObject classes but do want to emit their
own signales zim has it's own `SignalEmitter`class in `zim.signals`.


Keep in mind that with each `connect()` an object reference is created to the
handler method. The reference is kept by the object that is being connected to
and is only broken when that object is being destroyed. So if you do

	object_A.connect('some-signal', object_B.some_method)

then object_B will not be destroyed as long as object_A is alive. On the other
hand, if object_A is destroyed, object_B simply doesn't get any signals anymore.

The `SignalConnectorMixin` class keeps track of the connections it made, which
helps in cleaning up.


## Coding Style & Conventions

See the python style guide for best practices. Some additional remarks:
* In contradiction to the style guide, zim uses `TAB`s (not spaces) with a
  tabstop set to the equivalent of 4 spaces
* Only use "assert" for checks that could be removed when code is stable, these
  statements could be optimized away
* Writing test cases is good, full test coverage is better.
  Run `./test.py --cover` to get a coverage report.
* Use signals for colaboration between classes where possible
* Signal handlers have a method name starting with "do_" (for signals of the
  same classe) or "on_" (for signals of collaborating classes)


### Test suite

Zim comes with a full test suite, it can be executed using the `test.py`
script. See `test.py --help` for it's commandline options.

This test suite will at least test for all plugins that they can be loaded
and contain proper information.

To test the specific functions of your plugin, you need to write your own test
case. Have a look at test cases of existing plugins for ideas how to do that.

## Merge request checklist

If you think your plugin is a good fit for the list of default plugins in Zim
you can create your own branch of the zim source code with your plugin added
and open a merge request.

Some things to consider:
* Make sure the plugin not only solves your own problem, but is also applicable
  for a more generic use case that many people may have
* Each plugin should have it's own page in the user manual that explains what
  it does and how to use it.
* Each plugin should come with its own test cases for the test suite. Other
  developers may not use your plugin, so if it breaks later on it may go
  undetected unless there is a test case for it.

Also see [CONTRIBUTING.md](./CONTRIBUTING.md) for more guidelines on getting
new features accepted for the main repository.

## How to ...

*If your answer is not in this list, see if any of the default plugins do
something similar and inspect the code.*

### Let a plugin handle a specific URL scheme
The PageView object defines a signal `activate-link`. An extension object
can connect to this signal and check the link that is being opened. If it
matches the URL scheme of interest you can handle it and return `True` to let
the PageView know it should not try to open this link itself.

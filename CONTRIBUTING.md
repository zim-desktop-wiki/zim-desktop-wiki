Contributing
============

Thank you for considering to contribute to the zim desktop wiki project. Zim
is an open source project and run by volunteers, so all help is welcome.


**Help wanted:** there are many issues in the bug tracker that need someone to pick
them up. To get started please have a look at the
[good first issue](https://github.com/zim-desktop-wiki/zim-desktop-wiki/labels/good%20first%20issue)
and
[plugin idea](https://github.com/zim-desktop-wiki/zim-desktop-wiki/labels/plugin%20idea) labels.


## Other resources
* Code repository:
  https://github.com/zim-desktop-wiki/zim-desktop-wiki
* Bug tracker and feature requests:
  https://github.com/zim-desktop-wiki/zim-desktop-wiki/issues
* Public wiki:
  https://www.zim-wiki.org/wiki/
* Mailing list:
  https://launchpad.net/~zim-wiki
* IRC Channel:
  #zim-wiki on Freenode IRC network. (Access from your web browser https://webchat.freenode.net/?channels=%23zim-wiki .)


## Filing a bug report
To file a bug report, please go to the bug tracker at
https://github.com/zim-desktop-wiki/zim-desktop-wiki/issues

* Make sure the issue is not already in the list by trying out a few key words
  in the search box
* Describe what you did and what happened in such a way that another user can
  follow step by step and reproduce the same result
* Please include information on your operating system, language settings, and
  other relevant context information

## Requesting new functionality
Also feature requests can go in the bug tracker. In this case:

* Please provide a use case description, explain the problem you are trying to
  solve with the proposed feature before describing the solution. This allows
  other users to think along and maybe improve on your solution.
* Make sure the use case is generic enough that it will benefit other users
  as well. If it is highly tailored for your specific work flow, changes are
  that no-one will work on it.


## Getting started with the code

See [README.md](./README.md) for instructions to setup zim from source code. Checkout
the github repository at https://github.com/zim-desktop-wiki/zim-desktop-wiki
to get the latest development branch.

The zim code is kept under version control using the git version control system.
See the website for documentation on using this system: https://git-scm.com/


## Bug fixes
For obvious bugs with simple fixes a merge request can be opened directly.
These should be very easy to review and merge. If you consider something a bug
even though the code does what it is supposed to do, please discuss first on
the mailing list or through am issue ticket.


## Adding new features
Many features can be added through a plugin. Where possible this is the
preferred way of extending zim. Using a plugins allows adding lot of
configurability via the plugin preferences and properties while keeping the
core interfaces simple.

See [PLUGIN_WRITING.md](./PLUGIN_WRITING.md) for documentation on writing plugins. Also if you want
to work on the core functionality, this is a good introduction on the code
structure.

Only very generic features that are obviously useful for all users should be
part of the core package. When in doubt please discuss first - either via the
mailing list or via a github issue ticket.

In some cases there is a good compromise by extending the core functionality
with certain capabilities, but exposing the user interface to take advantage of
these capabilities via a plugin. An example of this is the support for tags;
tags are part of the core wiki parsing methods, however to see a special index
view for tags you need to enable a plugin.

### Test suite

Zim comes with a full test suite, it can be executed using the `test.py`
script. See `test.py --help` for it's commandline options.

It is good practice to run the full suite before committing to a development
branch and especially before generating a merge request. This should ensures the
new patch doesn't break any existing code.

For any but the most trivial fixes test cases should be written to ensure the
functionality works as designed and to avoid breaking it again at a later time.
You'll surprise how often the same bug comes back after some time if there is
now test case is in place to detect it. Some bugs are just waiting to happen
again and again.

For writing tests have a look at the existing test code or check the
documentation for the "unittest" module in the python library.

A most useful tool for developing tests is looking at test **coverage**. When
you run `test.py` with the `--coverage` option the "coverage" module
will be loaded and a set of html pages will be generated in `./coverage`. In
these pages you can see line by line what code is called during the test run and
what lines of code go untested. It is hard to really get to 100% coverage, but
the target should be to get the coverage above at least 80% for each module.

If you added e.g. a new class and wrote a test case for it have a look at the
coverage to see what additional tests are needed to cover all code.

Of course having full coverage is no guarantee we cover all possible inputs, but
looking at coverage combined with writing tests for reported bugs


## Merge requests
Please use github to upload your patches and file a merge request towards the
zim repository. If you mention relevant issue numbers in the merge request it
will automatically be flagged in those issue tickets as well.

## Limitations
Main assumption about the whole file handling and page rendering is that files
are small enough that we can load them into memory several times. This seems a
valid assumption as notebooks are spread over many files. Having really huge
files with contents is outside the scope of the design. If this is what you want
to do, you probably need a more heavy duty text editor.


## Translations

To contribute to translations onlne please go to https://launchpad.net.

To test a new translation you can either download the snapshot from launchpad and run:

    ./tools/import-launchpad-translations.py launchpad-export.tar.gz


Or you can edit the template zim.pot with your favourite editor. In that case you should add you new .po file to the po/ directory.

After adding the .po file(s) you can compile the translation using:

    ./setup.py build_trans


### Italian Translation
A few remarks for Italian contributors. Please notice that these choices were
made earlier and we should respect them in order to assure consistency. It
doesn't mean that they're better than others. It's a just matter of stop
discussing and choosing one option instead of another. :)
-- *Mailing list post by  Marco Cevoli, Aug 29, 2012*

* plugin = estensione
* Please... = si elimina sempre
* pane = pannello (non riquadro)
* zim = lo mettiamo sempre in maiuscolo, Zim

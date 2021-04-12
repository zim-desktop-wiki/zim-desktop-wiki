Contributing
============

Thank you for considering contributing to the zim desktop wiki project. Zim
is an open-source project and run by volunteers, so all help is welcome.


**Help wanted:** there are many issues in the bug tracker that need someone to pick
them up. To get started, please have a look at the
[good first issue](https://github.com/zim-desktop-wiki/zim-desktop-wiki/labels/good%20first%20issue)
and
[plugin idea](https://github.com/zim-desktop-wiki/zim-desktop-wiki/labels/plugin%20idea) labels.

Also please read [WhyIsItNotDoneYet](https://github.com/zim-desktop-wiki/zim-desktop-wiki/wiki/WhyIsItNotDoneYet)
and [Development Planning](https://github.com/zim-desktop-wiki/zim-desktop-wiki/wiki/Planning) in the development wiki pages.


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

* Make sure the issue is not already in the list by trying out a few keywords
  in the search box
* Describe what you did and what happened in such a way that another user can
  follow step by step and reproduce the same result
* Please include information on your operating system, language settings, and
  other relevant context information

## Requesting new functionality
Also, feature requests can go in the bug tracker. In this case:

* Please provide a use case description, explain the problem you are trying to
solve with the proposed feature before describing the solution. This allows
  other users to think along and maybe improve on your solution.
* Make sure the use case is generic enough that it will benefit other users
  as well. If it is highly tailored for your specific work-flow, chances are
  that no-one will work on it (and no-one will want to maintain it in working
  state over the years).


## Getting started with the code

See [README.md](./README.md) for instructions to setup zim from source code. Checkout
the GitHub repository at https://github.com/zim-desktop-wiki/zim-desktop-wiki
to get the latest development branch.

zim code is kept under version control using the git version control system.
See the website for documentation on using this system: https://git-scm.com/

For indenting of python code, the code base uses TABs (not spaces) with a
tabstop set to the equivalent of 4 spaces. (Yes, I know this breaks the PEP8
recommendation.)


## Bug fixes
For obvious bugs with simple fixes, a merge request can be opened directly.
These should be very easy to review and merge. If you consider something a bug
even though the code does what it is supposed to do, please discuss it first on
the mailing list or through an issue ticket.


## Adding new features
Many features can be added through a plugin. Where possible this is the
preferred way of extending zim. Using a plugin greatly increases
configurability via the plugin preferences and properties while keeping the
core interfaces simple.

See [PLUGIN_WRITING.md](./PLUGIN_WRITING.md) for documentation on writing plugins. Also if you want
to work on the core functionality, this is a good introduction to the code
structure.

Only very generic features that are obviously useful for all users should be
part of the core package. When in doubt please discuss first - either via the
mailing list or via a GitHub issue ticket.

In some cases, there is a good compromise by extending the core functionality
with certain capabilities, but exposing the user interface to take advantage of
these capabilities via a plugin. An example of this is the support for tags;
tags are part of the core wiki parsing methods, however, to see a special index
view for tags you need to enable a plugin.

### Test suite

Zim comes with a full test suite, that can be executed using the `test.py`
script. See `test.py --help` for its commandline options.

It is good practice to run the full suite before committing to a development
branch and especially before generating a merge request. This should ensure that a
new patch doesn't break any existing code.

For any but the most trivial fixes test cases should be written to ensure the
functionality works as designed and to avoid breaking it again at a later time.
You'll be surprised how often the same bug comes back after some time if there is
no test case in place to detect it. Some bugs are just waiting to happen
again and again.

For writing tests, have a look at the existing test code or check the
documentation for the "unittest" module in the python library.

A most useful tool for developing tests is looking at test **coverage**. When
you run `test.py` with the `--coverage` option the "coverage" module
will be loaded and a set of HTML pages will be generated in `./coverage`. In
these pages, you can see line by line what code is called during the test run and
what lines of code go untested. It is hard to really get 100% coverage, so
the target should be to get a coverage of at least 80% for each module.

If you added e.g. a new class and wrote a test case for it, have a look at the
coverage to see what additional tests are needed to cover all of the code.

Of course, having full coverage is no guarantee that we covered all possible inputs, but
looking at coverage combined with writing tests for reported bugs should ensure
good project quality and satisfaction for all Zim users.


## Merge requests
Please use GitHub to upload your patches and file a merge request towards the
zim repository. If you mention relevant issue numbers in the merge request, it
will automatically be flagged in those issue tickets as well.

## Known Zim limitations
The main assumption about file handling and page rendering is that files
are small enough that we can load them into memory several times. This seems a
valid assumption as notebooks are spread over many files. Having really huge
files as wiki content is outside the scope of the design. If this is what you want
to do, you probably need a more heavy-duty text editor or another specialized
application.


## Translations

To contribute to translations online please go to either
https://hosted.weblate.org/projects/zim/master/
or https://hosted.weblate.org/projects/zim/develop/.

The first one (ending in "master") contains translation strings for the current/upcoming releases. The second one (ending in "develop") could contain strings for new features.

Or you can edit the template zim.pot with your favorite editor. In that case you should add you new .po file to the po/ directory.

After adding the .po file(s) you can compile the translation using:

    ./setup.py build_trans


### Italian Translation

> A few remarks for Italian contributors. Please notice that these choices were
made earlier and we should respect them in order to assure consistency. It
doesn't mean that they're better than others. It's a just matter of stop
discussing and choosing one option instead of another. :)
-- *Mailing list post by  Marco Cevoli, Aug 29, 2012*

* plugin = estensione
* Please... = si elimina sempre
* pane = pannello (non riquadro)
* zim = lo mettiamo sempre in maiuscolo, Zim

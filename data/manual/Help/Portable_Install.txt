Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.6
Creation-Date: 2020-09-29T20:48:08+02:00

====== Portable Install ======

To allow running zim in a "portable" install, you can configure the environment parameters which zim to e.g. looks up resources and [[Config Files]] with a special configuration file call ''environ.ini'' . This config file must be placed in the same folder where the zim script or zim executable is installed. The file can contain a section ''[Environment]'' where each key maps to an environment parameter.

When loading this file, the values are interpreted as file paths relative to the install directory. Also, environment parameters are interpreted as "''${NAME}''".

Thus a valid file could look like:

'''
[Environment]
HOME=../portable_home
XDG_CONFIG_HOME=../config
PATH=../bin:${PATH}
LANG=NL_nl
'''

This example overwrites the location for the home folder and for the default configuration folder. It also modifies the ''PATH'' to first look in a local folder before going to the default locations. And it changes the language in which zim will run.

Note that on windows paths need to be separated with a "'';''" instead of a "'':''".

This config file is parsed using the standard python library "''configparser''", not by the zim configuration library.

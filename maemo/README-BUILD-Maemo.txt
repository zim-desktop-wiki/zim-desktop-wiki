
In order to include maemo specific files in the build the 'ZIM_BUILD_TARGET'
environment variable need to be set to 'maemo' when running setup.py.

So for cross compiling the package for maemo run:

	ZIM_BUILD_TARGET=maemo ./setup.py install --root /path/to/package/dir


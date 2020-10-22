#!/usr/bin/python3

# This script is a wrapper around zim.main.main() for running zim as
# an application.


import sys
import os
import re

# Check if we run the correct python version
try:
	assert sys.version_info >= (3, 2)
except:
	print('zim needs python >= 3.2', file=sys.stderr)
	sys.exit(1)


def init_environment(installdir):
	# Try loading custom environment setup
	env_config_file = os.path.join(installdir, 'environ.ini')
	if os.path.exists(env_config_file):
		import configparser
		env_config = configparser.ConfigParser(allow_no_value=True, interpolation=configparser.ExtendedInterpolation())
		env_config.optionxform = lambda option: option # make parser case sensitive
		env_config['DEFAULT'].update((k, v.replace('$', '$$')) for k, v in os.environ.items()) # set default values for interpolating parameters
		env_config.read(env_config_file)
		for k, v in env_config['Environment'].items():
			os.environ[k] = _parse_environment_param(v, installdir)

	# Set data dir specific for windows installer
	data_dir = os.path.normpath(os.path.join(installdir, "share"))
	if os.path.exists(data_dir):
		dirs = os.environ.get("XDG_DATA_DIRS")
		if dirs:
			os.environ["XDG_DATA_DIRS"] = dirs + os.pathsep + data_dir
		else:
			os.environ["XDG_DATA_DIRS"] = data_dir


def _parse_environment_param(value, installdir):
	# interpolate relative paths
	# interpolate environment parameters
	parts = []
	for part in value.split(os.pathsep):
		if re.match(r'^\.\.?[/\\]', part): # ./ ../ .\ ..\
			parts.append(os.path.normpath(installdir + '/' + part))
		else:
			parts.append(part)

	return os.pathsep.join(parts)


def init_logging():
	import logging

	# Win32: must setup log file or it tries to write to $PROGRAMFILES
	# See http://www.py2exe.org/index.cgi/StderrLog
	# If startup is OK, this will be overruled in zim/main with per user log file
	if os.name == "nt" and (
		sys.argv[0].endswith('.exe')
		or sys.executable.endswith('pythonw.exe')
	):
		import tempfile
		dir = tempfile.gettempdir()
		if not os.path.isdir(dir):
			os.makedirs(dir)
		err_stream = open(dir + "\\zim.exe.log", "w")
		sys.stdout = err_stream
		sys.stderr = err_stream

	# Preliminary initialization of logging because modules can throw warnings at import
	logging.basicConfig(level=logging.WARN, format='%(levelname)s: %(message)s')
	logging.captureWarnings(True)


def init_macOS():
	# MacOS: Set the bundle name so that the application menu shows 'Zim'
	# instead of 'Python' (this requires the pyobjc package)
	try:
		from Foundation import NSBundle
		bundle = NSBundle.mainBundle()
		info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
		info['CFBundleName'] = 'Zim'
	except ImportError:
		pass


def main():
	if getattr(sys, 'frozen', False):
		# we are running in a bundle
		installdir = sys._MEIPASS
	else:
		installdir = os.path.dirname(os.path.abspath(__file__))

	# Run these functions before importing any application modules
	init_environment(installdir)
	init_logging()
	init_macOS()

	# Try importing our modules
	try:
		import zim
		import zim.main
	except ImportError:
		sys.excepthook(*sys.exc_info())
		print('ERROR: Could not find python module files in path:', file=sys.stderr)
		print(' '.join(map(str, sys.path)), file=sys.stderr)
		print('\nTry setting PYTHONPATH', file=sys.stderr)
		sys.exit(1)

	# Run the application and handle some exceptions
	try:
		exitcode = zim.main.main(*sys.argv)
		sys.exit(exitcode)
	except zim.main.GetoptError as err:
		print(sys.argv[0] + ':', err, file=sys.stderr)
		sys.exit(1)
	except zim.main.UsageError as err:
		print(err.msg, file=sys.stderr)
		sys.exit(1)
	except KeyboardInterrupt: # e.g. <Ctrl>C while --server
		print('Interrupt', file=sys.stderr)
		sys.exit(1)
	else:
		sys.exit(0)


if __name__ == '__main__':
	main()

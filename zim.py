#!/usr/bin/python3

# This script is a wrapper around zim.main.main() for running zim as
# an application.


import sys
import os
import re

# Check if we run the correct python version
REQUIRED_MINIMUM_PYTHON_VERSION = (3, 6)
USED_PYTHON_VERSION = sys.version_info
if USED_PYTHON_VERSION < REQUIRED_MINIMUM_PYTHON_VERSION:
	error_message = 'zim needs python >= {major}.{minor}'.format(
		major=REQUIRED_MINIMUM_PYTHON_VERSION[0],
		minor=REQUIRED_MINIMUM_PYTHON_VERSION[1],
	)
	sys.stderr.write(error_message)
	sys.exit(1)


def init_environment(installdir):
	# Automatically set data dir for a virtualenv install
	if sys.prefix != sys.base_prefix:
		zim_data_dir = os.path.join(sys.prefix, 'share')
		if os.path.isdir(zim_data_dir):
			os.environ['XDG_DATA_DIRS'] = os.pathsep.join(
					[zim_data_dir] + os.getenv('XDG_DATA_DIRS', '').split(os.pathsep)
				).strip(os.pathsep)

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

	if '-D' in sys.argv or '--debug' in sys.argv:
		level = logging.DEBUG
	elif '-V' in sys.argv or '--verbose' in sys.argv:
		level = logging.INFO
	else:
		level = logging.WARN

	logging.basicConfig(level=level, format='%(levelname)s: %(message)s')
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
	exit_code = 1
	try:
		exit_code = zim.main.main(*sys.argv)
	except zim.main.GetoptError as err:
		print(sys.argv[0] + ':', err, file=sys.stderr)
	except zim.main.UsageError as err:
		print(err.msg, file=sys.stderr)
	except KeyboardInterrupt: # e.g. <Ctrl>C while --server
		print('Interrupt', file=sys.stderr)
	except Exception as err:
		print(err, file=sys.stderr)
	finally:
		sys.exit(exit_code)


if __name__ == '__main__':
	main()

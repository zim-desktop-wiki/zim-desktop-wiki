# $Id: Makefile,v 1.6.1 2009/08/26 17:04:35 Bart de Koning Exp $
# 
# Based on Makefile v 1.6 2008/10/29 01:01:35 by ghantoos
# http://ghantoos.org/2008/10/19/creating-a-deb-package-from-a-python-setuppy/#setuppy

PYTHON=`which python`
DESTDIR=/
BUILDIR=$(CURDIR)/debian/zim
PROJECT=zim

all:
	$(PYTHON) setup.py build

help:
	@echo "make - Build sources"
	@echo "make test - Run test suite"
	@echo "make install - Install on local system"
	@echo "make source - Create source package"
	@echo "make buildrpm - Generate a rpm package"
	@echo "make builddeb - Generate a deb package"
	@echo "make clean - Get rid of scratch and byte files"

source:
	$(PYTHON) setup.py sdist $(COMPILE)

test:
	$(PYTHON) test.py

install:
	$(PYTHON) setup.py install --root $(DESTDIR) $(COMPILE)

buildrpm:
	$(PYTHON) setup.py bdist_rpm --post-install=rpm/postinstall --pre-uninstall=rpm/preuninstall

builddeb:
	# build the source package in the parent directory
	# then rename it to project_version.orig.tar.gz
	$(PYTHON) setup.py sdist $(COMPILE) --dist-dir=../ --prune
	rename -f 's/$(PROJECT)-(.*)\.tar\.gz/$(PROJECT)_$$1\.orig\.tar\.gz/' ../*
	# build the package
	dpkg-buildpackage -i -I -rfakeroot
	# clean up build files
	$(MAKE) -f $(CURDIR)/debian/rules clean

clean:
	$(PYTHON) setup.py clean
	rm -rf build/ MANIFEST tests/tmp/ locale/ man/
	find . -name '*.pyc' -delete

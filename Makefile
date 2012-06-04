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
	@echo "make epydoc - Generate API docs using 'epydoc'"
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
	dpkg-buildpackage -i -I -rfakeroot
	$(MAKE) -f $(CURDIR)/debian/rules clean

epydoc:
	epydoc --config ./epydoc.conf -v
	@echo -e '\nAPI docs are available in ./apidocs'

clean:
	$(PYTHON) setup.py clean
	rm -rf build/ MANIFEST tests/tmp/ locale/ man/ xdg/hicolor test_report.html
	find . -name '*.pyc' -delete
	find . -name '*.pyo' -delete
	find . -name '*~' -delete
	rm -fr debian/zim* debian/files debian/python-module-stampdir/

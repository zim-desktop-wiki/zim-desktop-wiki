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
	dpkg-buildpackage -i -I -rfakeroot
	$(MAKE) -f $(CURDIR)/debian/rules clean

clean:
	$(PYTHON) setup.py clean
	rm -rf build/ MANIFEST tests/tmp/ locale/ man/
	find . -name '*.pyc' -delete

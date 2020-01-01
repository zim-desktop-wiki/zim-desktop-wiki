#!/bin/bash
export LC_ALL=C.UTF-8

NEW="$1"
OLD=`python3 -c "import zim;print(zim.__version__)"`

SEMVER_REGEX="^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(\\-[0-9A-Za-z-]+(\\.[0-9A-Za-z-]+)*)?(\\+[0-9A-Za-z-]+(\\.[0-9A-Za-z-]+)*)?$"
if [[ ! "$NEW" =~ $SEMVER_REGEX ]]; then
  echo "Usage: $0 VERSION -- where version should match https://semver.org/ spec"
  exit 1
fi


# Update changelog

echo "Updating CHANGELOG.md"

TMP="/tmp/changelog.md"
DATE=`date +"%a %d %b %Y"` # Thu 28 Mar 2019

head CHANGELOG.md -n 7 > $TMP
echo "##  $NEW - $DATE" >> $TMP
git log --pretty=format:"* %s" --first-parent $OLD.. >> $TMP
echo "" >> $TMP
tail --lines=+7 CHANGELOG.md >> $TMP

vim $TMP || exit 1
cp $TMP CHANGELOG.md

# Update version numbers

echo "Updating zim/__init__.py"
sed -i "s/^__version__ =.*\$/__version__ = '$NEW'/" zim/__init__.py

echo "Updating website/pages/downloads.txt"
MONTH=`date +"%b %Y"`
sed -i "s/^=\+ Latest release: .*\$/===== Latest release: $NEW - $MONTH =====/" website/pages/downloads.txt


# Update debian version

echo "Updating debian/changelog"

DEBNEW=${NEW/-/~/} # Need "~" for release candidates in debian version
DEBDATE=`date +"%a, %d %b %Y %H:%M:%S %z"` #Thu, 28 Mar 2019 21:34:00 +0100

cat > ./debian/changelog << EOF
zim ($DEBNEW) unstable; urgency=medium

  * Update to release $DEBNEW

 -- Jaap Karssenberg <jaap.karssenberg@gmail.com>  $DEBDATE

EOF


# Update AppData

echo "Updating xdg/org.zim_wiki.Zim.appdata.xml"

./tools/add_release_to_appdata.py


# Build package & test it

echo "Building ..."

python3 ./test.py package || exit 1
./setup.py sdist
make builddeb
make clean
./tools/build_website.sh

lintian -Ivi ../zim_$DEBNEW\_*.changes


# Final steps are manual
cat << EOF

================================================================================

To finish release run:
git commit -a -m "Release $NEW"
git tag $NEW
git push
git push --tags

Then:
- Upload packages and html to website
- Email announcement to mailing list
EOF

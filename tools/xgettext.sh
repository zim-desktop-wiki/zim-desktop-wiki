echo 'Extracting translatable strings ...'
find zim -name '*.py' | sort | xgettext -f - -o translations/zim.pot
find data/templates -name '*.txt' | sort | xgettext -j -C -f - -o translations/zim.pot
find data/templates -name '*.html' | sort | xgettext -j -C -f - -o translations/zim.pot
echo 'Extracting comments ...'
./tools/extract_translator_comments.py

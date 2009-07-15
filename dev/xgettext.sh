echo 'Extracting translatable strings ...'
find zim -name '*.py' | sort | xgettext -f - -o zim.pot
echo 'Extracting comments ...'
./dev/extract_translator_comments.py

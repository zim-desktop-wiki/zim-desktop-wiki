#!/bin/sh
#
# ============================================================================
#
#   newton2zim v0.0.2
#
#       Attempt to do a sane conversion from a "Newton <= 0.0.9" style Desktop
#       Wiki to Zim style data files.
#
#   Copyright
#
#       newton2zim is Copyrighted ©2006 by Eugene Roux. All rights reserved.
#
#       This script is free software; you can redistribute it and/or modify
#       it under the same terms as Zim.
#
#       Thus newton2zim may be copied only under the terms of either the
#       Artistic License or the General Public License.
#
#       This script is distributed in the hope that it will be useful, but
#       WITHOUT ANY WARRANTY; without even the implied warranty of
#       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
#   Disclaimer
#
#       I really dislike legalese, but there are many fools out there...
#
# ============================================================================

FULL="=";

for ARG in $@; do
    if [ "x$1" == "x-n" ]; then
        NOTITLE=1;
        shift;
    elif [ "x$1" == "x-r" ]; then
        FULL="";
        shift;
    fi;
done;

NDIR=$HOME/.newton/data;
ZDIR=$1;

if [ "x${ZDIR}" == "x" ]; then
    cat <<-EOF

	Usage: `basename $0` [-n] [-r] <ZimRepositoryRoot>

	    Where:
	        -n      Suppress Page title generation (ie. you alrady have those)
	        -r      Reduce the Heading Depth (If your headings started at "=",
	                you probably want this...)

	        and
	            <ZimRepositoryRoot>
	                The full path of the repository you want to import your Newton
	                data into.

EOF
    exit 0;
fi

if [ ! -d ${NDIR} ]; then
    echo "Could not locate Newton's data directory for '${USER}'...";
    exit 1;
fi

n2zconv() {
    # Notes:
    #
    #  * '#' gets replaces by '*', effectively turning Newton numbered lists into Zim bullet lists
    #  * {{ }} gets converted to [[ ]] for non-local (starts with '/') files; images in my case
    #  * &, < and > gets converted from HTML entities to characters
    #
    sed -e "s/^@@@ \([^ ]*\)  *\(.*\),\(.*\) @\([0-9][0-9]:[0-9][0-9]:[0-9][0-9]\) */Updated \2 \1 \3 at \4\n/" \
        -e "/^@@@Never/d" \
        -e "s/^\*\* /\t\* /" \
        -e "s/^\*\*\* /\t\t\* /" \
        -e "s/^# /\* /" \
        -e "s/^## /\t\* /" \
        -e "s/^### /\t\t\* /" \
        -e "s/^====== *\(.*\)/\n# =${FULL} \1 ${FULL}=\n/" \
        -e "s/^===== *\(.*\)/\n# =${FULL} \1 ${FULL}=\n/" \
        -e "s/^==== *\(.*\)/\n# ==${FULL} \1 ${FULL}==\n/" \
        -e "s/^=== *\(.*\)/\n# ===${FULL} \1 ${FULL}===\n/" \
        -e "s/^== *\(.*\)/\n# ====${FULL} \1 ${FULL}====\n/" \
        -e "s/^= *\(.*\)/\n# =====${FULL} \1 ${FULL}=====\n/" \
        -e "s/<\/*del>/~~/g" \
        -e "s/&amp;/&/g" \
        -e "s/&lt;/</g" \
        -e "s/&gt;/>/g" \
        -e "s/{{ *\([^\/][^}]*\)}}/[[\1]]/g" \
        -e "s/{{ *\([^|]*\)|*[^}]*}}/{{\1}}/g" \
        -e "s/\n# =/\n=/" | \
        cat -s
};

find ${NDIR}| while read NODE; do
    ZEQUIV=`echo "${NODE}"| sed -e "s|${NDIR}|${ZDIR}|" -e "s| |_|g" -e "s|&|and|g"`;

    if [ -d "${NODE}" ]; then
        if [ ! -d "${ZEQUIV}" ]; then
            mkdir "${ZEQUIV}";
        fi;
    else
        if [ ! $NOTITLE ]; then
            # Generate a title based on the Newton nodename
            echo "${NODE}"| sed "s|.*/\(.*\)|====== \1 ======|" > "${ZEQUIV}.txt";
        fi;
        cat "${NODE}"| n2zconv >> "${ZEQUIV}.txt";
    fi;
done;

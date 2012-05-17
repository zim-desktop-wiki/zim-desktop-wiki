${SegmentFile}

${SegmentPre}
	FindFirst $0 $1 $DataDirectory\.local\share\zim\application\*.desktop
	${DoUntil} $1 == ""
		${ReplaceInFile} "$DataDirectory\.local\share\zim\application\$1" "$LastDrive\" "$CurrentDrive\"
		${ReplaceInFile} "$DataDirectory\.local\share\zim\application\$1" "$LastDrive/" "$CurrentDrive/"
		FindNext $0 $1
	${Loop}
	FindClose $0
!macroend

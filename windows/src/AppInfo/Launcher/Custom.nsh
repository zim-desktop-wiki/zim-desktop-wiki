${SegmentFile}

${SegmentPre}
	ExpandEnvStrings $0 %PAL:AppDir%\ZimDesktopWiki\prepare_notebook_list.js
	ExecWait `"$SYSDIR\wscript.exe" "$0"` $0
	StrCmp $0 "0" SegmentPreOk SegmentPreFailed
	SegmentPreFailed:
		MessageBox MB_ICONEXCLAMATION "Failed to create notebooks.list."
		Abort
	SegmentPreOk:
!macroend

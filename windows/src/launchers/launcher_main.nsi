Icon "../../../icons/zim.ico"
!ifdef IS_PORTABLE
	Name "Zim Desktop Wiki Portable"
	Caption "Zim Desktop Wiki Portable"
	!ifdef IS_DEBUG
		OutFile "../../build/ZimDesktopWiki/Zim Desktop Wiki Portable (Debug Mode).exe"
	!else
		OutFile "../../build/ZimDesktopWiki/Zim Desktop Wiki Portable.exe"
	!endif
!else
	Name "Zim Desktop Wiki"
	Caption "Zim Desktop Wiki"
	!ifdef IS_DEBUG
		OutFile "../../build/ZimDesktopWiki/zim_debug.exe"
	!else
		Abort "You shouldn't be building this version of the launcher."
	!endif
!endif

SilentInstall silent
AutoCloseWindow true
ShowInstDetails nevershow
RequestExecutionLevel user
SetCompressor lzma

!include "FileFunc.nsh"
!insertmacro GetParameters

var zimPath
var myTemp
var zimParms
!ifdef IS_PORTABLE
	var portableRoot
!endif

Section ""
	${GetParameters} $zimParms

	Call findPaths
	!ifdef IS_PORTABLE
		StrCpy $myTemp "$portableRoot\App\Temp"
		CreateDirectory $myTemp
		CreateDirectory "$portableRoot\App\Config"
		CreateDirectory "$portableRoot\App\Cache"
		CreateDirectory "$portableRoot\App\Data"
	
		System::Call 'Kernel32::SetEnvironmentVariable(t, t)i ("HOME", "$portableRoot").r0'
		StrCmp $0 0 envError
		System::Call 'Kernel32::SetEnvironmentVariable(t, t)i ("TEMP", "$myTemp").r0'
		StrCmp $0 0 envError
		System::Call 'Kernel32::SetEnvironmentVariable(t, t)i ("XDG_CONFIG_HOME", "$portableRoot\App\Config").r0'
		StrCmp $0 0 envError
		System::Call 'Kernel32::SetEnvironmentVariable(t, t)i ("XDG_CONFIG_DIRS", "").r0'
		StrCmp $0 0 envError
		System::Call 'Kernel32::SetEnvironmentVariable(t, t)i ("XDG_DATA_HOME", "$portableRoot\App\Data").r0'
		StrCmp $0 0 envError
		System::Call 'Kernel32::SetEnvironmentVariable(t, t)i ("XDG_DATA_DIRS", "").r0'
		StrCmp $0 0 envError
		System::Call 'Kernel32::SetEnvironmentVariable(t, t)i ("XDG_CACHE_HOME", "$portableRoot\App\Cache").r0'
		StrCmp $0 0 envError
	!else
	  StrCpy $myTemp "$TEMP"
	!endif

  !ifdef IS_DEBUG
		MessageBox MB_ICONINFORMATION|MB_OK \
			'Zim Desktop Wiki will be started in Debug mode.$\r$\n\
			$\r$\n\
			After you perform the activity you want to see in the log file, completely \
			close Zim, and then the log file in "$myTemp\zim.exe.log" will be \
			displayed in Notepad.' \
			IDNO quit
		ExecWait '"$zimPath" --standalone --debug $zimParms'
		Exec 'notepad "$myTemp\zim.exe.log"'
	!else
		Exec '"$zimPath" $zimParms'
	!endif

!ifdef IS_PORTABLE
	envError:
		Abort "Failed to set environment variables."
!endif

!ifdef IS_DEBUG
quit:
!endif
SectionEnd

Function findPaths
	StrCpy $zimPath "$EXEDIR\zim.exe"
	!ifdef IS_PORTABLE
		Push $EXEDIR
		Call GetParent
		Call GetParent
		Pop $portableRoot
	!endif
	IfFileExists "$EXEDIR\share\zim\zim.png" found

	StrCpy $zimPath "$EXEDIR\ZimDesktopWiki\zim.exe"
	!ifdef IS_PORTABLE
		Push $EXEDIR
		Call GetParent
		Pop $portableRoot
	!endif
	IfFileExists "$EXEDIR\ZimDesktopWiki\share\zim\zim.png" found

	StrCpy $zimPath "$EXEDIR\App\ZimDesktopWiki\zim.exe"
	!ifdef IS_PORTABLE
		StrCpy $portableRoot $EXEDIR
	!endif
	IfFileExists "$EXEDIR\App\ZimDesktopWiki\share\zim\zim.png" found
	
	Abort "Couldn't find zim.exe."

found:
FunctionEnd

!ifdef IS_PORTABLE
	 ; GetParent
	 ; input, top of stack  (e.g. C:\Program Files\Foo)
	 ; output, top of stack (replaces, with e.g. C:\Program Files)
	 ; modifies no other variables.
	 ;
	 ; Usage:
	 ;   Push "C:\Program Files\Directory\Whatever"
	 ;   Call GetParent
	 ;   Pop $R0
	 ;   ; at this point $R0 will equal "C:\Program Files\Directory"
	Function GetParent
		Exch $R0
		Push $R1
		Push $R2
		Push $R3
	 
		StrCpy $R1 0
		StrLen $R2 $R0
	 
		loop:
			IntOp $R1 $R1 + 1
			IntCmp $R1 $R2 get 0 get
			StrCpy $R3 $R0 1 -$R1
			StrCmp $R3 "\" get
		Goto loop
	 
		get:
			StrCpy $R0 $R0 -$R1
	 
			Pop $R3
			Pop $R2
			Pop $R1
			Exch $R0 
	FunctionEnd
!endif ; ifdef IS_DEBUG
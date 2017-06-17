; Script generated with the Venis Install Wizard

; Define your application name
!define APPNAME "Zim Desktop Wiki Portable"

; Define VER and BUILDDATE
!include "..\build\version-and-date.nsi"

!define APPNAMEANDVERSION "Zim Desktop Wiki Portable ${VER}"

; Main Install settings
Name "${APPNAMEANDVERSION}"
InstallDir "$DESKTOP\Zim Desktop Wiki Portable"
OutFile "..\..\dist\zim-desktop-wiki-portable-${VER}.exe"
RequestExecutionLevel user
SetCompressor /SOLID lzma

; Modern interface settings
!include "MUI.nsh"

!include "sections.nsh"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\zim.exe"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "zim-logo-big.bmp" ; optional
!define MUI_ICON "..\..\icons\zim.ico"

!define MUI_DIRECTORYPAGE_TEXT_TOP \
	"Setup will install ${APPNAME} in the following folder."

!define MUI_COMPONENTSPAGE_SMALLDESC

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Set languages (first is default language)
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_RESERVEFILE_LANGDLL


Section "-Main program" SecProgramFiles

	IfFileExists $INSTDIR check_is_empty no_check_is_empty
		check_is_empty:
		Push $INSTDIR
		Call isEmptyDir
		Pop $0
		${If} $0 == 0
			MessageBox MB_OK \
				"A Portable installation must be performed in a new empty folder. You can \
				copy your notebooks in after installation.$\r$\n\
				$\r$\n\
				Please rename your old Zim Desktop Wiki Portable folder before installing \
				this new version."
			Abort
		${EndIf}
		
	no_check_is_empty:

	; ----
	; Okay to go...
	; ----

	; Set Section properties
	SetOverwrite on

	SetOutPath "$INSTDIR\App\ZimDesktopWiki\"

	; Include main files; skip the 'portable' and 'portable debug' launchers
	File /r \
		/x "zim.exe.log" \
		/x "Zim *Portable*.exe" \
		"..\build\ZimDesktopWiki\*.*"

	SetOutPath "$INSTDIR\"

	File "/oname=zim.exe" "..\build\ZimDesktopWiki\Zim Desktop Wiki Portable.exe"
	File "Zim Desktop Wiki for Windows README.rtf"

	SetOutPath "$INSTDIR\App\"
	File "/oname=launch zim with debug mode.exe" "..\build\ZimDesktopWiki\Zim Desktop Wiki Portable (Debug Mode).exe"

	CreateDirectory "$INSTDIR\Notebooks"

SectionEnd


Function isEmptyDir
  # Stack ->                    # Stack: <directory>
  Exch $0                       # Stack: $0
  Push $1                       # Stack: $1, $0
  FindFirst $0 $1 "$0\*.*"
  strcmp $1 "." 0 _notempty
    FindNext $0 $1
    strcmp $1 ".." 0 _notempty
      ClearErrors
      FindNext $0 $1
      IfErrors 0 _notempty
        FindClose $0
        Pop $1                  # Stack: $0
        StrCpy $0 1
        Exch $0                 # Stack: 1 (true)
        goto _end
     _notempty:
       FindClose $0
       ClearErrors
       Pop $1                   # Stack: $0
       StrCpy $0 0
       Exch $0                  # Stack: 0 (false)
  _end:
FunctionEnd

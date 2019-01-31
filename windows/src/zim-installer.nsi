; Script generated with the Venis Install Wizard

; Define your application name
!define APPNAME "Zim Desktop Wiki"

; Define VER and BUILDDATE
!include "..\build\version-and-date.nsi"

!define APPNAMEANDVERSION "Zim Desktop Wiki ${VER}"

; Main Install settings
Name "${APPNAMEANDVERSION}"
InstallDir "$PROGRAMFILES\Zim Desktop Wiki"
InstallDirRegKey HKLM "Software\${APPNAME}" ""
OutFile "..\..\dist\zim-desktop-wiki-setup-${VER}.exe"
SetCompressor /SOLID lzma

; Modern interface settings
!include "MUI.nsh"

; Register Extension function
!include "registerExtension.nsh"

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
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Set languages (first is default language)
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_RESERVEFILE_LANGDLL

Section "-Main program" SecProgramFiles

	; Clear installation folder, to be sure to get rid of orphaned files
	RMDir /r "$INSTDIR"

	; Set Section properties
	SetOverwrite on

	SetOutPath "$INSTDIR\"

	; Include main files; skip the 'portable' and 'portable debug' launchers
	File /r \
		/x "zim.exe.log" \
		/x "Zim *Portable*.exe" \
		"..\build\ZimDesktopWiki\*.*"

	File "..\..\icons\zim.ico"
	File "Zim Desktop Wiki for Windows README.rtf"

SectionEnd

Section "Start Menu shortcut" SecStartShortcut

	CreateDirectory "$SMPROGRAMS\Zim Desktop Wiki"
	CreateShortCut "$SMPROGRAMS\Zim Desktop Wiki\Zim.lnk" "$INSTDIR\zim.exe"
	CreateShortCut "$SMPROGRAMS\Zim Desktop Wiki\Zim (Debug Mode).lnk" "$INSTDIR\zim_debug.exe"
	CreateShortCut "$SMPROGRAMS\Zim Desktop Wiki\README for Zim for Windows.lnk" "$INSTDIR\Zim Desktop Wiki for Windows README.rtf"
	CreateShortCut "$SMPROGRAMS\Zim Desktop Wiki\Uninstall.lnk" "$INSTDIR\uninstall.exe"

SectionEnd

Section /o "Desktop shortcut" SecDesktopShortcut

	; Set Section properties
	SetOverwrite on

	; Set Section Files and Shortcuts
	CreateShortCut "$DESKTOP\Zim Desktop Wiki.lnk" "$INSTDIR\zim.exe"

SectionEnd

Section ".zim file association" SecAssociate

	${registerExtension} "$INSTDIR\zim.exe" ".zim" "Zim Desktop Wiki" "$INSTDIR\zim.ico"

SectionEnd

Section "Create registry keys and uninstaller" SecUninstall

	WriteRegStr HKLM "Software\${APPNAME}" "" "$INSTDIR"
	WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
	WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"
	WriteUninstaller "$INSTDIR\uninstall.exe"

SectionEnd


; Modern install component descriptions
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
	!insertmacro MUI_DESCRIPTION_TEXT ${SecStartShortcut} \
	"Install a shortcut to Zim in your Start Menu."
	!insertmacro MUI_DESCRIPTION_TEXT ${SecDesktopShortcut} \
	"Install a shortcut to Zim on your Desktop."
	!insertmacro MUI_DESCRIPTION_TEXT ${SecAssociate} \
	"Associate .zim files with Zim."
	!insertmacro MUI_DESCRIPTION_TEXT ${SecUninstall} \
	"Create uninstaller and registry keys necessary for uninstallation."
!insertmacro MUI_FUNCTION_DESCRIPTION_END


;Uninstall section
Section Uninstall

	;Remove file association
	${unregisterExtension} ".zim" "Zim Desktop Wiki"

	;Remove from registry...
	DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
	DeleteRegKey HKLM "SOFTWARE\${APPNAME}"

	; Delete self
	Delete "$INSTDIR\uninstall.exe"

	; Delete configuration
	RMDir /r "$APPDATA\zim"

	; Remove remaining directories
	RMDir "$SMPROGRAMS\Zim Desktop Wiki"
	RMDir /r "$INSTDIR"

	; Detel desktop icon and Start Menu shortcuts
	SetShellVarContext all
	Delete "$DESKTOP\Zim Desktop Wiki.lnk"
	RMDir /r "$SMPROGRAMS\Zim Desktop Wiki"
	SetShellVarContext current
	Delete "$DESKTOP\Zim Desktop Wiki.lnk"
	RMDir /r "$SMPROGRAMS\Zim Desktop Wiki"

SectionEnd

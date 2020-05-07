; Script generated with the Venis Install Wizard

; directories relative to windows/dist/zim

; Define your application name

!define APPNAME "Zim Desktop Wiki"
!define ID "zim-wiki"
!define DESC "Zim is a graphical text editor used to maintain a collection of wiki pages."

!define APPNAMEANDVERSION "${APPNAME} ${VERSION}"

; Main Install settings
Name "${APPNAMEANDVERSION}"
InstallDir "$PROGRAMFILES\${APPNAME}"
InstallDirRegKey HKLM "Software\${APPNAME}" ""
OutFile "..\zim-desktop-wiki-${VERSION}-setup.exe"
SetCompressor /SOLID lzma

; Modern interface settings
!include "MUI.nsh"

; Register Extension function
!include "..\..\src\registerExtension.nsh"

!include "sections.nsh"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\zim.exe"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "..\..\src\zim-logo-big.bmp" ; optional
!define MUI_ICON "..\..\..\icons\zim.ico"

!define MUI_DIRECTORYPAGE_TEXT_TOP \
	"Setup will install ${APPNAME} in the following folder."

!define MUI_COMPONENTSPAGE_SMALLDESC

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_LICENSE "..\..\..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Set languages (first is default language)
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "German"
!insertmacro MUI_RESERVEFILE_LANGDLL

Var INST_BIN

Section "-Main program" SecProgramFiles
    SetShellVarContext all

	; Clear installation folder, to be sure to get rid of orphaned files
	RMDir /r "$INSTDIR"

	; Set Section properties
	SetOverwrite on

	SetOutPath "$INSTDIR\"

	; Include main files; skip the 'portable' and 'portable debug' launchers
	File /r \
		/x "zim.exe.log" \
		"*.*"

	File "..\..\..\icons\zim.ico"

	StrCpy $INST_BIN "$INSTDIR\zim.exe"

    ; Add application entry
    WriteRegStr HKLM "Software\${APPNAME}\${ID}\Capabilities" "ApplicationDescription" "${DESC}"
    WriteRegStr HKLM "Software\${APPNAME}\${ID}\Capabilities" "ApplicationName" "${APPNAME}"

    ; Register application entry
    WriteRegStr HKLM "Software\RegisteredApplications" "${APPNAME}" "Software\${APPNAME}\${ID}\Capabilities"

    ; Register app paths
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\App Paths\zim.exe" "" "$INST_BIN"

	CreateShortCut "$SMPROGRAMS\${APPNAME}.lnk" "$INST_BIN"
SectionEnd

Section /o "Desktop shortcut" SecDesktopShortcut

	; Set Section properties
	SetOverwrite on

	; Set Section Files and Shortcuts
	CreateShortCut "$DESKTOP\Zim Desktop Wiki.lnk" "$INST_BIN"

SectionEnd

Section ".zim file association" SecAssociate

	${registerExtension} "$INST_BIN" ".zim" "${APPNAME}" "$INSTDIR\zim.ico"

SectionEnd

Section "Create registry keys and uninstaller" SecUninstall

	WriteRegStr HKLM "Software\${APPNAME}" "" "$INSTDIR"
	WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
	WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"
	WriteUninstaller "$INSTDIR\uninstall.exe"

SectionEnd


; Modern install component descriptions
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
	!insertmacro MUI_DESCRIPTION_TEXT ${SecDesktopShortcut} \
	"Install a shortcut to Zim on your Desktop."
	!insertmacro MUI_DESCRIPTION_TEXT ${SecAssociate} \
	"Associate .zim files with Zim."
	!insertmacro MUI_DESCRIPTION_TEXT ${SecUninstall} \
	"Create uninstaller and registry keys necessary for uninstallation."
!insertmacro MUI_FUNCTION_DESCRIPTION_END


;Uninstall section
Section Uninstall
    SetShellVarContext all
    SetAutoClose true

	;Remove file association
	${unregisterExtension} ".zim" "${APPNAME}"

	;Remove from registry...
	DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
	DeleteRegKey HKLM "Software\${APPNAME}"

	; Delete self
	Delete "$INSTDIR\uninstall.exe"

	; Delete configuration
	RMDir /r "$APPDATA\zim"

	; Remove remaining directories
	Delete "$SMPROGRAMS\${APPNAME}.lnk"
	RMDir /r "$INSTDIR"

	; Detel desktop icon and Start Menu shortcuts
	SetShellVarContext all
	Delete "$DESKTOP\${APPNAME}.lnk"
	RMDir /r "$SMPROGRAMS\${APPNAME}"
	SetShellVarContext current
	Delete "$DESKTOP\${APPNAME}.lnk"
	RMDir /r "$SMPROGRAMS\${APPNAME}"

SectionEnd

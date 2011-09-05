; Script generated with the Venis Install Wizard

; Define your application name
!define APPNAME "Zim Desktop Wiki"

; Define VER and BUILDDATE
!include "version-and-date.nsi"

!define APPNAMEANDVERSION "Zim Desktop Wiki ${VER} for Windows"

; Main Install settings
Name "${APPNAMEANDVERSION}"
InstallDir "$PROGRAMFILES\Zim Desktop Wiki"
InstallDirRegKey HKLM "Software\${APPNAME}" ""
OutFile "..\dist\Zim-setup-${VER}_${BUILDDATE}.exe"

; Modern interface settings
!include "MUI.nsh"

; Register Extension function
!include "registerExtension.nsh"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\zim.exe"

!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "zim-logo-big.bmp" ; optional
!define MUI_ICON "zim.ico"

!define MUI_DIRECTORYPAGE_TEXT_TOP \
	"Setup will install ${APPNAME} in the following folder. \
	$\r$\r \
	BE SURE TO CHOOSE ANOTHER FOLDER NOW if you want to install Zim \
	to a portable storage device."

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


Section "-Main program" SecDesktopFiles

	SectionIn 1

	RMDir /r "$INSTDIR"

	; Set Section properties
	SetOverwrite on

	; Set Section Files and Shortcuts
	SetOutPath "$INSTDIR\"
	File /r /x .svn /x Zim-setup*.exe /x "zim.exe.log" "build\*.*"
	File "zim.ico"

SectionEnd

Section "-Portable program" SecPortableFiles

	SectionIn 2

	RMDir /r "$INSTDIR\App"

	; Set Section properties
	SetOverwrite on

	; Set Section Files and Shortcuts
	SetOutPath "$INSTDIR\App"
	File /r /x .svn /x Zim-setup*.exe /x "zim.exe.log" "build\*.*"
	File "zim.ico"
	
	; Launcher
	SetOutPath "$INSTDIR"
	File "start_zim_portable.js"
	File /oname=README.txt "README.portable.txt"

SectionEnd


SectionGroup "Desktop" GroupDesktop

	Section "Start Menu shortcut" SecStartShortcut
	
		SectionIn 1
	
		CreateDirectory "$SMPROGRAMS\Zim Desktop Wiki"
		CreateShortCut "$SMPROGRAMS\Zim Desktop Wiki\Zim.lnk" "$INSTDIR\zim.exe"
		CreateShortCut "$SMPROGRAMS\Zim Desktop Wiki\Uninstall.lnk" "$INSTDIR\uninstall.exe"
	
	SectionEnd
	
	Section "Desktop shortcut" SecDesktopShortcut

		SectionIn 1
	
		; Set Section properties
		SetOverwrite on

		; Set Section Files and Shortcuts
		CreateShortCut "$DESKTOP\Zim Desktop Wiki.lnk" "$INSTDIR\zim.exe"
	
	SectionEnd
	
	Section ".zim file association" SecAssociate
		
		SectionIn 1
		${registerExtension} "$INSTDIR\zim.exe" ".zim" "Zim Desktop Wiki" "$INSTDIR\zim.ico"
		
	SectionEnd
	
	Section "Create Registry Keys and Uninstaller" SecUninstall
	
		SectionIn 1
		WriteRegStr HKLM "Software\${APPNAME}" "" "$INSTDIR"
		WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
		WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"
		WriteUninstaller "$INSTDIR\uninstall.exe"
	
	SectionEnd

SectionGroupEnd

SectionGroup "Portable" GroupPortable

	Section "Set portable mode" SecPortable

		SectionIn 2

	SectionEnd

SectionGroupEnd


; Modern install component descriptions
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
	!insertmacro MUI_DESCRIPTION_TEXT ${GroupDesktop} \
	"Install to this computer."
	!insertmacro MUI_DESCRIPTION_TEXT ${SecStartShortcut} \
	"Install a shortcut to Zim in your Start Menu."
	!insertmacro MUI_DESCRIPTION_TEXT ${SecDesktopShortcut} \
	"Install a shortcut to Zim on your Desktop."
	!insertmacro MUI_DESCRIPTION_TEXT ${SecAssociate} \
	"Associate .zim files with Zim."
	!insertmacro MUI_DESCRIPTION_TEXT ${SecUninstall} \
	"Create uninstaller and registry keys necessary for uninstallation."
	!insertmacro MUI_DESCRIPTION_TEXT ${GroupPortable} \
	"Install to portable storage device."
	!insertmacro MUI_DESCRIPTION_TEXT ${SecPortable} \
	"Set the installed application to portable mode (does not use Registry nor My Documents or Program Files folders)."
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

InstType "Desktop Install"
InstType "Portable Install"

; eof
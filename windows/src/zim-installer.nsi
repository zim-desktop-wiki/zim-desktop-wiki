!define APPNAME "Zim Desktop Wiki"
!define UNINSTKEY "404fbece-3a0a-4f4f-b1f1-82ce46af9696" ; a random GUID
!define ID "zim-wiki"
!define DESC "Zim is a graphical text editor used to maintain a collection of wiki pages."

!define APPNAMEANDVERSION "${APPNAME} ${VERSION}"
!define DEFAULTNORMALDESTINATON "$ProgramFiles\${APPNAME}"
!define DEFAULTPORTABLEDESTINATON "$Desktop\${APPNAME}"

; Main Install settings
Name "${APPNAMEANDVERSION}"
OutFile "..\zim-desktop-wiki-${VERSION}-setup.exe"
RequestExecutionlevel highest
SetCompressor /SOLID lzma

Var NormalDestDir
Var PortableDestDir
Var PortableMode

!include LogicLib.nsh
!include FileFunc.nsh
!include MUI2.nsh

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
Page Custom PortableModePageCreate PortableModePageLeave
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_LICENSE "..\..\..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE English
!insertmacro MUI_RESERVEFILE_LANGDLL


Function .onInit
StrCpy $NormalDestDir "${DEFAULTNORMALDESTINATON}"
StrCpy $PortableDestDir "${DEFAULTPORTABLEDESTINATON}"

${GetParameters} $9

ClearErrors
${GetOptions} $9 "/?" $8
${IfNot} ${Errors}
    MessageBox MB_ICONINFORMATION|MB_SETFOREGROUND "\
      /PORTABLE : Extract application to USB drive etc$\n\
      /S : Silent install$\n\
      /D=%directory% : Specify destination directory$\n"
    Quit
${EndIf}

ClearErrors
${GetOptions} $9 "/PORTABLE" $8
${IfNot} ${Errors}
    StrCpy $PortableMode 1
    StrCpy $0 $PortableDestDir
${Else}
    StrCpy $PortableMode 0
    StrCpy $0 $NormalDestDir
    ${If} ${Silent}
        Call RequireAdmin
    ${EndIf}
${EndIf}

${If} $InstDir == ""
    ; User did not use /D to specify a directory, 
    ; we need to set a default based on the install mode
    StrCpy $InstDir $0
${EndIf}
Call SetModeDestinationFromInstdir
FunctionEnd


Function RequireAdmin
UserInfo::GetAccountType
Pop $8
${If} $8 != "admin"
    MessageBox MB_ICONSTOP "You need administrator rights to install ${APPNAME}"
    SetErrorLevel 740 ;ERROR_ELEVATION_REQUIRED
    Abort
${EndIf}
FunctionEnd


Function SetModeDestinationFromInstdir
${If} $PortableMode = 0
    StrCpy $NormalDestDir $InstDir
${Else}
    StrCpy $PortableDestDir $InstDir
${EndIf}
FunctionEnd


Function PortableModePageCreate
Call SetModeDestinationFromInstdir ; If the user clicks BACK on the directory page we will remember their mode specific directory
!insertmacro MUI_HEADER_TEXT "Install Mode" "Choose how you want to install ${APPNAME}."
nsDialogs::Create 1018
Pop $0
${NSD_CreateLabel} 0 10u 100% 24u "Select install mode:"
Pop $0
${NSD_CreateRadioButton} 30u 50u -30u 8u "Normal install"
Pop $1
${NSD_CreateRadioButton} 30u 70u -30u 8u "Portable"
Pop $2
${If} $PortableMode = 0
    SendMessage $1 ${BM_SETCHECK} ${BST_CHECKED} 0
${Else}
    SendMessage $2 ${BM_SETCHECK} ${BST_CHECKED} 0
${EndIf}
nsDialogs::Show
FunctionEnd


Function PortableModePageLeave
${NSD_GetState} $1 $0
${If} $0 <> ${BST_UNCHECKED}
    StrCpy $PortableMode 0
    StrCpy $InstDir $NormalDestDir
    Call RequireAdmin
${Else}
    StrCpy $PortableMode 1
    StrCpy $InstDir $PortableDestDir
${EndIf}
FunctionEnd


Var INST_BIN


Section "-Main program" SecProgramFiles
    SetShellVarContext all

    ; Clear installation folder, to be sure to get rid of orphaned files
    RMDir /r "$INSTDIR"

    ; Set Section properties
    SetOverwrite on

    SetOutPath "$INSTDIR\"

    File /r \
        /x "zim.exe.log" \
        "*.*"

    File "..\..\..\icons\zim.ico"

    StrCpy $INST_BIN "$INSTDIR\zim.exe"

    ${If} $PortableMode = 0
        ; Add application entry
        WriteRegStr HKLM "Software\${APPNAME}\${ID}\Capabilities" "ApplicationDescription" "${DESC}"
        WriteRegStr HKLM "Software\${APPNAME}\${ID}\Capabilities" "ApplicationName" "${APPNAME}"

        ; Register application entry
        WriteRegStr HKLM "Software\RegisteredApplications" "${APPNAME}" "Software\${APPNAME}\${ID}\Capabilities"

        ; Register app paths
        WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\App Paths\zim.exe" "" "$INST_BIN"

        CreateShortCut "$SMPROGRAMS\${APPNAME}.lnk" "$INST_BIN"
    ${EndIf}

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

    ${If} $PortableMode = 0
        WriteRegStr HKLM "Software\${APPNAME}" "" "$INSTDIR"

        WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}" "DisplayName" "${APPNAME}"
        WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}" "UninstallString" "$INSTDIR\uninstall.exe"
        WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}" "DisplayIcon" "$INSTDIR\zim.ico"
    ${EndIf}

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


Section Uninstall

    SetShellVarContext all
    SetAutoClose true

    ;Remove file association
    ${unregisterExtension} ".zim" "${APPNAME}"

    ;Remove from registry...
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}"
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

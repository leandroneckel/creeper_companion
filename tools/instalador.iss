; Instalador do Creeper Companion (Inno Setup 6). Gerado por tools/build_exe.py, que passa
; /DAppVersion e /DAppGuid e prepara o ícone e as imagens em build/.
;
; Instala só pro usuário (sem pedir administrador) em %LOCALAPPDATA%\Programs\CreeperCompanion,
; onde o próprio creeper consegue se atualizar depois. O progresso (save) fica em %APPDATA% e
; não é apagado ao desinstalar, a não ser que a pessoa peça.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppGuid
  #error Passe /DAppGuid (o build_exe.py faz isso)
#endif
#define AppExe "CreeperCompanion.exe"
#define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"

[Setup]
AppId={{{#AppGuid}}
AppName=Creeper Companion
AppVersion={#AppVersion}
AppVerName=Creeper Companion {#AppVersion}
AppPublisher=Leandro Neckel
AppPublisherURL=https://github.com/leandroneckel/creeper_companion
AppSupportURL=https://github.com/leandroneckel/creeper_companion/issues
AppUpdatesURL=https://leandroneckel.github.io/creeper_companion/
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\CreeperCompanion
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=CreeperCompanion-Setup
SetupIconFile=..\build\creeper.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName=Creeper Companion
WizardStyle=modern dynamic
WizardImageFile=..\build\instalador-grande.png,..\build\instalador-grande-2x.png
WizardSmallImageFile=..\build\instalador-pequeno.png,..\build\instalador-pequeno-2x.png
Compression=lzma2
SolidCompression=yes
; se ele estiver aberto (reinstalando por cima), fecha antes de trocar o arquivo
CloseApplications=force
RestartApplications=no

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na área de trabalho"
Name: "autostart"; Description: "Abrir o creeper junto com o Windows"
Name: "updates"; Description: "Avisar quando sair versão nova (ele pergunta ao GitHub a cada 6 horas)"

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Creeper Companion"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\Creeper Companion"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; o mesmo valor que Configurações → "Iniciar com o sistema" liga e desliga
Root: HKCU; Subkey: "{#RunKey}"; ValueType: string; ValueName: "CreeperCompanion"; ValueData: """{app}\{#AppExe}"""; Tasks: autostart
; a escolha sobre versão nova vai pro creeper, que lê e apaga ao abrir (creeper/updater.py)
Root: HKCU; Subkey: "Software\CreeperCompanion"; ValueType: dword; ValueName: "AvisarVersaoNova"; ValueData: 1; Flags: uninsdeletekey; Tasks: updates
Root: HKCU; Subkey: "Software\CreeperCompanion"; ValueType: dword; ValueName: "AvisarVersaoNova"; ValueData: 0; Flags: uninsdeletekey; Tasks: not updates

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o Creeper Companion agora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "FecharCreeper"

[UninstallDelete]
; sobras da atualização automática
Type: files; Name: "{app}\{#AppExe}.*.old"
Type: files; Name: "{app}\{#AppExe}.new"
Type: dirifempty; Name: "{app}"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKEY_CURRENT_USER, '{#RunKey}', 'CreeperCompanion');
    if not UninstallSilent and
       (MsgBox('Apagar também o creeper salvo (nome, nível, itens e configurações)?' + #13#10 +
               'Se não apagar, ele volta do jeitinho que estava quando você instalar de novo.',
               mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
      DelTree(ExpandConstant('{userappdata}\CreeperCompanion'), True, True, True);
  end;
end;

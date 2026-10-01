; Instalador da apresentação (Inno Setup 6).
;
;   iscc /DPasta=dist\CursosLivres-Apresentacao /DVersao=1.0.5 apresentacao\instalador.iss
;
; Instala para o usuário atual, sem pedir administrador, em uma pasta onde o
; programa pode gravar o banco da demonstração (ao lado do executável).

#ifndef Pasta
  #define Pasta "..\dist\CursosLivres-Apresentacao"
#endif
#ifndef Versao
  #define Versao "1.0.0"
#endif
#define Exe "Iniciar apresentacao.exe"

[Setup]
AppId={{6C1F4E2B-8D3A-4B7E-9F21-3C5A7D9E0B14}
AppName=Cursos Livres - Apresentação
AppVersion={#Versao}
AppPublisher=Cursos Livres
DefaultDirName={localappdata}\Programs\Cursos Livres - Apresentacao
DefaultGroupName=Cursos Livres
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=CursosLivres-Apresentacao-Instalador
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Cursos Livres - Apresentação

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalho"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "{#Pasta}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Cursos Livres - Apresentação"; Filename: "{app}\{#Exe}"; WorkingDir: "{app}"
Name: "{group}\Leia-me"; Filename: "{app}\LEIA-ME.txt"
Name: "{userdesktop}\Cursos Livres - Apresentação"; Filename: "{app}\{#Exe}"; WorkingDir: "{app}"; Tasks: atalho

[Run]
Filename: "{app}\{#Exe}"; Description: "Abrir a apresentação agora"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Banco e comprovantes criados durante as apresentações.
Type: filesandordirs; Name: "{app}\dados-da-apresentacao"

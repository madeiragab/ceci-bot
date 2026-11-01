# Gera o Ceci Bot.exe (PyInstaller, modo pasta) em %LOCALAPPDATA%\Programs\Ceci Bot e o atalho na área de trabalho.
# Uso (na pasta do projeto): powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1
$proj = Split-Path -Parent $PSScriptRoot
$work = Join-Path $env:TEMP 'cecibot_build'   # caminho curto: o PyInstaller não lida bem com caminhos muito longos
$dist = Join-Path $env:LOCALAPPDATA 'Programs'
New-Item -ItemType Directory -Force $work | Out-Null
python -c "import comtypes.client; comtypes.client.GetModule('UIAutomationCore.dll')"  # gera comtypes.gen (UI Automation) antes de empacotar
Get-Process -Name 'Ceci Bot' -ErrorAction SilentlyContinue | Stop-Process -Force
python -m PyInstaller --noconfirm --clean --windowed --name 'Ceci Bot' --icon "$proj\assets\icon\ceci.ico" `
    --add-data "$proj\assets\sprites;assets\sprites" --add-data "$proj\assets\frames.json;assets" `
    --add-data "$proj\assets\animations.json;assets" --add-data "$proj\assets\falas.json;assets" --add-data "$proj\assets\icon;assets\icon" `
    --add-data "$proj\assets\ceci_personality.txt;assets" `
    --collect-all playwright --collect-data tzdata --collect-submodules comtypes `
    --exclude-module numpy --exclude-module scipy --exclude-module PIL --exclude-module tkinter `
    --distpath $dist --workpath "$work\build" --specpath $work "$proj\main.py"
Remove-Item -Recurse -Force $work
$exe = Join-Path $dist 'Ceci Bot\Ceci Bot.exe'
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Ceci Bot.lnk'
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = $exe; $s.WorkingDirectory = Split-Path $exe; $s.IconLocation = "$exe,0"; $s.Description = 'Ceci Bot'
$s.Save()
Write-Host "Pronto: $exe (atalho: $lnk)"

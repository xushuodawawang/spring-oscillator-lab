"""用 Windows 自带的 32 位 IExpress 打包离线网页，避开 Python 系统依赖。"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
target = root / "dist/win7"
html = target / "SpringOscillatorLab-Win7.html"
assert html.exists(), "先运行 build_offline.py"
with tempfile.TemporaryDirectory(prefix="spring-win7-") as folder:
    stage = Path(folder)
    shutil.copy2(html, stage / html.name)
    # 先复制到固定本地目录，再打开浏览器；IExpress 清理临时文件不会影响页面。
    bat = r'''@echo off
setlocal
set "labdir=%LOCALAPPDATA%\SpringOscillatorLabWin7"
if not exist "%labdir%" mkdir "%labdir%"
copy /y "%~dp0SpringOscillatorLab-Win7.html" "%labdir%\SpringOscillatorLab-Win7.html" >nul
if errorlevel 1 exit /b 1
set "labpage=%labdir%\SpringOscillatorLab-Win7.html"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" "%labpage%" & exit /b)
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (start "" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" "%labpage%" & exit /b)
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (start "" "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" "%labpage%" & exit /b)
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (start "" "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" "%labpage%" & exit /b)
start "" "%labpage%"
'''
    (stage / "launch.cmd").write_text(bat, encoding="ascii", newline="\r\n")
    sed = f'''[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName={stage / 'SpringOscillatorLab-Win7-v1.2.exe'}
FriendlyName=Spring Oscillator Lab - Win7 Offline
AppLaunched=cmd.exe /c launch.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
SourceFiles=SourceFiles
[Strings]
FILE0="SpringOscillatorLab-Win7.html"
FILE1="launch.cmd"
[SourceFiles]
SourceFiles0={stage}\\
[SourceFiles0]
%FILE0%=
%FILE1%=
'''
    sedpath = stage / "package.sed"
    sedpath.write_text(sed, encoding="ascii", newline="\r\n")
    iexpress = Path(os.environ["SystemRoot"]) / "SysWOW64/iexpress.exe"
    subprocess.run([str(iexpress), "/N", "/Q", str(sedpath)], cwd=stage,
                   creationflags=subprocess.CREATE_NO_WINDOW, check=True, timeout=90)
    exe = stage / "SpringOscillatorLab-Win7-v1.2.exe"
    assert exe.exists(), "IExpress 没有产生 EXE"
    shutil.copy2(exe, target / exe.name)
    print(target / exe.name, exe.stat().st_size)

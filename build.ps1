param([string]$PythonCommand = "py", [string]$ExecutableName = "SpringOscillatorLab-v1.2")
$ErrorActionPreference = "Stop"
if ($ExecutableName -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]*$') { throw "Invalid executable name" }
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    if ($PythonCommand -eq "py") { & py -3.12 -m venv .venv }
    else { & $PythonCommand -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw "Python virtual environment creation failed" }
}
if (Test-Path -LiteralPath "requirements-lock.txt") {
    & .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
} else {
    & .\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
}
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Physics tests failed; packaging stopped" }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --noupx --name $ExecutableName --add-data "index.html;." --collect-data rapidocr_onnxruntime --collect-all onnxruntime --hidden-import uvicorn.logging --hidden-import uvicorn.loops.asyncio --hidden-import uvicorn.protocols.http.h11_impl --hidden-import uvicorn.lifespan.on launcher.py
if ($LASTEXITCODE -ne 0) { throw "EXE packaging failed" }
Get-Item -LiteralPath "dist\$ExecutableName.exe" | Select-Object FullName,Length

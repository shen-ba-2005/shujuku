$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath '.venv\Scripts\pyinstaller.exe')) {
    throw '未找到 PyInstaller。请先执行：.\.venv\Scripts\python.exe -m pip install pyinstaller==6.13.0'
}

& '.venv\Scripts\pyinstaller.exe' --noconfirm --clean 'launcher.spec'
if ($LASTEXITCODE -ne 0) { throw '启动器打包失败，请查看上方日志。' }
Write-Host "启动器已生成：$projectRoot\dist\屿账.exe"

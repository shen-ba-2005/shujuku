param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

$pyinstaller = Join-Path $projectRoot '.venv\Scripts\pyinstaller.exe'
if (-not (Test-Path -LiteralPath $pyinstaller)) {
    throw '未找到 PyInstaller。请先执行：.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt'
}

$mysqlSource = $env:SHUJUKU_MYSQL_HOME
if (-not $mysqlSource) {
    $mysqlSource = 'C:\Program Files\MySQL\MySQL Server 8.0'
}
if (-not (Test-Path -LiteralPath (Join-Path $mysqlSource 'bin\mysqld.exe'))) {
    throw "未找到 MySQL Server。请设置 SHUJUKU_MYSQL_HOME，或先安装 MySQL 8.0。"
}

if (-not $SkipBuild) {
    & $pyinstaller --noconfirm launcher.spec
    if ($LASTEXITCODE -ne 0) { throw '启动器打包失败。' }
}

$release = Join-Path $projectRoot 'release\屿账'
New-Item -ItemType Directory -Path $release -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot 'dist\屿账.exe') -Destination $release

# A self-contained release keeps the MySQL server beside the launcher. The
# user still only double-clicks 屿账.exe; no PATH or terminal setup is needed.
$mysqlDestination = Join-Path $release 'mysql'
New-Item -ItemType Directory -Path $mysqlDestination -Force | Out-Null
Get-ChildItem -LiteralPath $mysqlSource -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $mysqlDestination -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $projectRoot '使用说明.txt') -Destination $release -Force
Write-Host "发布包已生成：$release"
Write-Host '用户双击 屿账.exe 即可启动；数据会保存到用户 LocalAppData。'

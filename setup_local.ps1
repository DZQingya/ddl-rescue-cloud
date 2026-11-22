﻿param([switch]$CheckOnly, [switch]$SetupOnly)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

function Find-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @{ Path = $py.Source; Args = @("-3") } }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @{ Path = $python.Source; Args = @() } }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
        "C:\Python312\python.exe",
        "C:\Python311\python.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return @{ Path = $candidate; Args = @() } }
    }
    return $null
}

Write-Host "DDL 急救站 · 一键本地部署" -ForegroundColor Cyan
$pythonCmd = Find-Python
if (-not $pythonCmd) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "未检测到 Python，也没有 winget。请先安装 Python 3.12+，或使用手动步骤启动。"
    }
    Write-Host "未检测到 Python，正在通过 winget 自动安装 Python 3.12..." -ForegroundColor Yellow
    & winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    $pythonCmd = Find-Python
    if (-not $pythonCmd) {
        throw "Python 安装完成后仍未找到 python。请关闭窗口后重新双击一键部署.bat。"
    }
}

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "创建本地 Python 环境..." -ForegroundColor Cyan
    & $pythonCmd.Path @($pythonCmd.Args) -m venv .venv
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "虚拟环境创建失败，请检查 Python 安装。"
}

Write-Host "安装/更新依赖..." -ForegroundColor Cyan
& $venvPython -m pip install --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败。" }

if ($CheckOnly) {
    Write-Host "环境检查通过。" -ForegroundColor Green
    exit 0
}

$desktop = [Environment]::GetFolderPath("Desktop")
$launcher = Join-Path $root "启动.bat"
if (Test-Path -LiteralPath $launcher) {
    $shortcutPath = Join-Path $desktop "DDL急救站.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launcher
    $shortcut.WorkingDirectory = $root
    $shortcut.Description = "打开 DDL 急救站本地工作台"
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,21"
    $shortcut.Save()
    Write-Host "已创建桌面快捷方式：DDL急救站" -ForegroundColor Green
}

if ($SetupOnly) {
    Write-Host "安装完成，可从桌面或包内启动.bat重新打开。" -ForegroundColor Green
    exit 0
}

Write-Host "启动本地服务..." -ForegroundColor Green
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "launch_local.ps1")

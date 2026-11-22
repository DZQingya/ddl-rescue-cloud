param([switch]$CheckOnly, [switch]$NoBrowser)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "尚未安装本地环境。请先双击「一键部署.bat」。"
}

function Get-PortOwner {
    $conn = Get-NetTCPConnection -State Listen -LocalPort 8501 -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return $null }
    return Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue
}

$owner = Get-PortOwner
if ($owner) {
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($owner.ParentProcessId)" -ErrorAction SilentlyContinue
    $grand = if ($parent) { Get-CimInstance Win32_Process -Filter "ProcessId=$($parent.ParentProcessId)" -ErrorAction SilentlyContinue } else { $null }
    $ownerCmd = [string]$owner.CommandLine
    $parentCmd = if ($parent) { [string]$parent.CommandLine } else { "" }
    $ownerExe = [string]$owner.ExecutablePath
    $parentExe = if ($parent) { [string]$parent.ExecutablePath } else { "" }
    $isDdlRescue = ($ownerCmd -match 'streamlit.*work\\app\.py') -or ($parentCmd -match 'streamlit.*work\\app\.py')
    $samePackage = $ownerExe -like "$root\.venv\Scripts\python.exe" -or $parentExe -like "$root\.venv\Scripts\python.exe"

    if (-not $isDdlRescue) {
        throw "端口 8501 被其他程序占用（PID $($owner.ProcessId)），为避免误杀，启动已停止。请关闭占用程序后重试。"
    }

    if ($samePackage) {
        if ($CheckOnly) { Write-Output "CURRENT_PACKAGE_RUNNING"; exit 0 }
        Write-Host "当前版本已经在运行，直接打开浏览器。" -ForegroundColor Green
        if (-not $NoBrowser) { Start-Process "http://localhost:8501" }
        exit 0
    }

    if ($CheckOnly) { Write-Output "OLD_DDL_PROCESS_WOULD_BE_STOPPED"; exit 0 }
    Write-Host "检测到旧版 DDL 急救站占用端口，正在切换到当前版本..." -ForegroundColor Yellow
    $toStop = @($owner.ProcessId)
    if ($parent -and ($parent.Name -match 'python|cmd|powershell')) { $toStop += $parent.ProcessId }
    if ($grand -and $grand.Name -eq 'cmd.exe' -and ([string]$grand.CommandLine) -match '启动\.bat|一键部署\.bat') { $toStop += $grand.ProcessId }
    foreach ($procId in ($toStop | Sort-Object -Unique)) { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue }
    $deadline = (Get-Date).AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 250
        $still = Get-NetTCPConnection -State Listen -LocalPort 8501 -ErrorAction SilentlyContinue
    } while ($still -and (Get-Date) -lt $deadline)
    if ($still) { throw "旧进程已尝试停止，但端口 8501 仍未释放。" }
    Write-Host "旧实例已停止，启动当前版本。" -ForegroundColor Green
}

if ($CheckOnly) { Write-Output "PORT_FREE"; exit 0 }
if (-not $NoBrowser) {
    Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList @("-NoProfile", "-Command", "Start-Sleep -Seconds 3; Start-Process 'http://localhost:8501'")
}
& $venvPython -m streamlit run work\app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
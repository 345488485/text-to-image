param(
    [switch]$InitializeAdmin,
    [string]$Username = 'admin',
    [switch]$Restart,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root 'platform\.venv\Scripts\python.exe'
$frontend = Join-Path $root 'platform\frontend'
if (!(Test-Path -LiteralPath $python)) { throw '请先按 platform/README.md 安装平台独立环境。' }

if ($InitializeAdmin) {
    Push-Location (Join-Path $root 'platform')
    try {
        & $python -m backend.cli create-admin --username $Username
        if ($LASTEXITCODE -ne 0) { throw '管理员初始化失败。' }
    } finally { Pop-Location }
    return
}

& (Join-Path $root 'platform\start-frontend.ps1') -CheckOnly
if (!(Test-Path -LiteralPath (Join-Path $frontend 'node_modules'))) { throw '请先安装前端依赖，详见platform/README.md。' }
# Only verified project entrypoints/listeners may be stopped; never kill by image name.
function Test-PlatformProcess($process) {
    if (!$process -or !$process.CommandLine) { return $false }
    $command = $process.CommandLine.Replace('/', '\')
    $base = [regex]::Escape($root)
    return $command -match ($base + '\\platform\\(serve\.py|start-frontend\.ps1|frontend\\.*\\vite\\bin\\vite\.js)(["\s]|$)')
}
function Get-PlatformListeners {
    # Avoid CIM/WMI: its provider may hang even when no platform process exists.
    foreach ($line in (& "$env:SystemRoot\System32\netstat.exe" -ano -p tcp)) {
        $columns = $line.Trim() -split '\s+'
        if ($columns.Count -eq 5 -and $columns[0] -eq 'TCP' -and $columns[3] -eq 'LISTENING' -and $columns[1] -match ':(8000|5173)$') {
            [pscustomobject]@{LocalPort=[int]$Matches[1]; OwningProcess=[int]$columns[4]}
        }
    }
}
$ports = @(8000,5173)
$listeners = @(Get-PlatformListeners)
if ($Restart) {
    $stopArgs = @('--root', $root)
    foreach ($listener in $listeners) { $stopArgs += @('--listener', [string]$listener.OwningProcess) }
    foreach ($name in @('backend.pid','frontend.pid')) {
        $pidFile = Join-Path $root "platform\logs\$name"
        if (Test-Path -LiteralPath $pidFile) {
            $recorded = 0
            if ([int]::TryParse((Get-Content -LiteralPath $pidFile -Raw).Trim(), [ref]$recorded) -and $recorded -gt 0) {
                $stopArgs += @('--recorded', [string]$recorded)
            }
        }
    }
    & $python (Join-Path $root 'platform\tools\stop_platform.py') @stopArgs
    if ($LASTEXITCODE -ne 0) { throw 'Could not safely stop previous platform instance.' }
    $deadline = (Get-Date).AddSeconds(15)
    do {
        $listeners = @(Get-PlatformListeners)
        if (!$listeners.Count) { break }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $deadline)
}
if ($listeners.Count) { throw 'Platform ports 8000/5173 are occupied. Use start.bat to restart this project, or close unrelated applications.' }

# The backend creates admin/123456 only for an empty database and locks all business APIs until password change.
$logs = Join-Path $root 'platform\logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backend = Start-Process -FilePath $python -ArgumentList @('-u',"`"$root\platform\serve.py`"") -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$logs\backend-$stamp.stdout.log" -RedirectStandardError "$logs\backend-$stamp.stderr.log" -PassThru
$backend.Id | Set-Content (Join-Path $logs 'backend.pid')
$shell = (Get-Process -Id $PID).Path
$web = Start-Process -FilePath $shell -ArgumentList @('-NoProfile','-File',"`"$root\platform\start-frontend.ps1`"") -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$logs\frontend-$stamp.stdout.log" -RedirectStandardError "$logs\frontend-$stamp.stderr.log" -PassThru
$web.Id | Set-Content (Join-Path $logs 'frontend.pid')
Write-Host "平台已启动：http://127.0.0.1:5173 。后台PID=$($backend.Id)，前端PID=$($web.Id)。日志：$logs"
if (!$NoBrowser) { Start-Process 'http://127.0.0.1:5173' }

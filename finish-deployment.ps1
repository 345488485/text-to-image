param([int]$TorchProcessId = 0, [int]$ModelProcessId = 0)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:UV_CACHE_DIR = "$PSScriptRoot\.runtime\uv"
$env:TEMP = "$PSScriptRoot\.runtime\tmp"
$env:TMP = $env:TEMP
$env:HF_HOME = "$PSScriptRoot\.runtime\hf"
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:DO_NOT_TRACK = '1'
$env:UV_HTTP_TIMEOUT = '180'
$env:UV_CONCURRENT_DOWNLOADS = '4'
$python = "$PSScriptRoot\.venv\Scripts\python.exe"
try {
    if ($TorchProcessId) { Wait-Process -Id $TorchProcessId -ErrorAction SilentlyContinue }
    & $python -c 'import torch; print(torch.__version__, torch.version.cuda); assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0)); print((torch.ones(2,device="cuda")+1).tolist())'
    if ($LASTEXITCODE) { throw 'CUDA PyTorch installation failed; see install-torch.log.' }
    if ((Get-PSDrive F).Free -lt 8GB) { throw 'Less than 8GiB free before dependencies; no files deleted.' }
    & uv --no-cache pip install --python $python --index-url https://pypi.org/simple -r "$PSScriptRoot\.runtime\source\ComfyUI-master\requirements.txt" 'torch==2.9.1+cu128' 'torchvision==0.24.1+cu128'
    if ($LASTEXITCODE) { throw 'ComfyUI dependency installation failed.' }
    & uv pip check --python $python
    if ($LASTEXITCODE) { throw 'Dependency validation failed.' }
    if ($ModelProcessId) { Wait-Process -Id $ModelProcessId -ErrorAction SilentlyContinue }
    # Verify complete files without starting a second download.
    & $python download_models.py --endpoint https://hf-mirror.com --preflight-only
    if ($LASTEXITCODE) { throw 'Model manifest validation failed.' }
    $manifest = Get-Content .runtime\model-manifest.json -Raw | ConvertFrom-Json
    if ($manifest.remaining_bytes -ne 0) { throw 'Model downloads incomplete; preserve .part files and resume download_models.py.' }
    if ((Get-PSDrive F).Free -lt 5GB) { throw 'Less than 5GiB free; not starting inference.' }
    $shell = (Get-Process -Id $PID).Path
    $server = Start-Process -FilePath $shell -ArgumentList @('-NoProfile','-File',"`"$PSScriptRoot\start-moss.ps1`"") -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput "$PSScriptRoot\.runtime\server.stdout.log" -RedirectStandardError "$PSScriptRoot\.runtime\server.stderr.log" -PassThru
    $server.Id | Set-Content .runtime\server.pid
    $ready = $false
    for ($i = 0; $i -lt 90; $i++) {
        if ($server.HasExited) { throw 'Server exited; see server.stderr.log.' }
        try { $null = Invoke-RestMethod http://127.0.0.1:8188/system_stats -TimeoutSec 3; $ready = $true; break } catch { Start-Sleep -Seconds 2 }
    }
    if (!$ready) { throw 'Server readiness timeout.' }
    & $python smoke_test.py
    if ($LASTEXITCODE) { throw 'Generation failed; see smoke-history.json and server.stderr.log.' }
    & uv pip freeze --python $python | Set-Content .runtime\requirements-installed.txt
    'VERIFIED: local PNG generated; http://127.0.0.1:8188' | Set-Content .runtime\deployment-status.txt
} catch {
    "FAILED: $_" | Set-Content .runtime\deployment-status.txt
    Write-Error $_
    exit 1
}

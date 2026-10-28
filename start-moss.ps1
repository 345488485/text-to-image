$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:TEMP = Join-Path $PSScriptRoot '.runtime\tmp'
$env:TMP = $env:TEMP
$env:HF_HOME = Join-Path $PSScriptRoot '.runtime\hf'
$env:TORCH_HOME = Join-Path $PSScriptRoot '.runtime\torch'
$env:PYTHONNOUSERSITE = '1'
$main = Join-Path $PSScriptRoot '.runtime\source\ComfyUI-master\main.py'
if (!(Test-Path -LiteralPath $main)) { throw 'ComfyUI source download is not complete.' }
& .\.venv\Scripts\python.exe $main --listen 127.0.0.1 --port 8188 --lowvram --preview-method none --extra-model-paths-config "$PSScriptRoot\extra_model_paths.yaml" --output-directory "$PSScriptRoot\output" --temp-directory "$PSScriptRoot\.runtime\tmp" --user-directory "$PSScriptRoot\user" --disable-auto-launch
exit $LASTEXITCODE

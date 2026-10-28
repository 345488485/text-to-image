param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$frontend = Join-Path $PSScriptRoot 'frontend'
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$node = if ($nodeCommand) { $nodeCommand.Source } else { $null }
if (!$node) {
    foreach ($candidate in @('E:\nodejs\node.exe', (Join-Path $env:ProgramFiles 'nodejs\node.exe'))) {
        if (Test-Path -LiteralPath $candidate) { $node = $candidate; break }
    }
}
if (!$node) { throw 'Node.js not found. Install Node.js or add node.exe to PATH.' }
$vite = Join-Path $frontend 'node_modules\vite\bin\vite.js'
if (!(Test-Path -LiteralPath $vite)) { throw 'Frontend dependencies missing: node_modules/vite/bin/vite.js' }
# Child tools must also find Node when launched from Explorer instead of Codex.
$env:Path = (Split-Path -Parent $node) + ';' + $env:Path
if ($CheckOnly) { Write-Host "Frontend runtime ready: $node"; return }
Push-Location (Join-Path $frontend 'apps\moss')
try {
    & $node $vite --host 127.0.0.1 --port 5173 --strictPort
    $result = $LASTEXITCODE
} finally { Pop-Location }
exit $result

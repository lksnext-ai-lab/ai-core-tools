# PostToolUse (Edit|Write): run eslint on an edited frontend TS/TSX file and feed results back as context.
# Best-effort and NON-BLOCKING: skips silently if eslint isn't installed; always exits 0.
$ErrorActionPreference = 'SilentlyContinue'

$raw = [Console]::In.ReadToEnd()
if (-not $raw) { exit 0 }
try { $data = $raw | ConvertFrom-Json } catch { exit 0 }

$fp = $data.tool_input.file_path
if (-not $fp) { exit 0 }
if ($fp -notmatch 'frontend[\\/].*\.(ts|tsx)$') { exit 0 }

$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { exit 0 }
$frontendDir = Join-Path $projDir 'frontend'
if (-not (Test-Path (Join-Path $frontendDir 'node_modules\.bin'))) { exit 0 }  # eslint unavailable; skip

$full = Resolve-Path $fp -ErrorAction SilentlyContinue
if (-not $full) { exit 0 }

Push-Location $frontendDir
$result = & npx --no-install eslint $full.Path 2>&1 | Out-String
$code = $LASTEXITCODE
Pop-Location

if ($code -ne 0 -and $result.Trim()) {
    $ctx = "eslint flagged the file just edited ($([System.IO.Path]::GetFileName($fp))):`n" + $result.Trim()
    $out = @{ hookSpecificOutput = @{ hookEventName = 'PostToolUse'; additionalContext = $ctx } }
    $out | ConvertTo-Json -Depth 5 -Compress
}
exit 0

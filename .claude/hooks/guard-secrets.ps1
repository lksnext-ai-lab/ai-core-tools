# PreToolUse guard (Edit|Write): block editing secret/sensitive files via the agent.
# Reads hook JSON from stdin; denies by emitting a permissionDecision. Always exits 0 so it never breaks the session.
$ErrorActionPreference = 'SilentlyContinue'

$raw = [Console]::In.ReadToEnd()
if (-not $raw) { exit 0 }
try { $data = $raw | ConvertFrom-Json } catch { exit 0 }

$fp = $data.tool_input.file_path
if (-not $fp) { exit 0 }
$name = Split-Path $fp -Leaf

$blocked = $false

# .env and variants, but allow templates (.env.example/.sample/.template)
if ($name -match '^\.env' -and $name -notmatch '\.(example|sample|template)$') { $blocked = $true }

foreach ($p in @('\.pem$','\.key$','^id_rsa','credentials','^secrets?\.(json|ya?ml)$')) {
    if ($name -match $p) { $blocked = $true; break }
}

# Never let the agent edit local (untracked) settings overrides.
if ($fp -match 'settings\.local\.json$') { $blocked = $true }

if ($blocked) {
    $reason = "Blocked by .claude guard: '$name' looks like a secret/sensitive file. Editing secrets through the agent is disabled. If this is intentional, edit it manually."
    $out = @{ hookSpecificOutput = @{ hookEventName = 'PreToolUse'; permissionDecision = 'deny'; permissionDecisionReason = $reason } }
    $out | ConvertTo-Json -Depth 5 -Compress
}
exit 0

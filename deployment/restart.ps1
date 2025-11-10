param (
    [string]$Host = $env:TALATG_DEPLOY_HOST,
    [string]$User = $env:TALATG_DEPLOY_USER,
    [string]$RemotePath = $env:TALATG_DEPLOY_PATH
)

if (-not $Host) { throw "Set TALATG_DEPLOY_HOST or pass -Host." }
if (-not $User) { throw "Set TALATG_DEPLOY_USER or pass -User." }
if (-not $RemotePath) { throw "Set TALATG_DEPLOY_PATH or pass -RemotePath." }

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { throw "ssh not found in PATH." }

$remoteCommand = "cd $RemotePath/deployment && docker compose restart arbitrage-bot"
& ssh "$User@$Host" $remoteCommand


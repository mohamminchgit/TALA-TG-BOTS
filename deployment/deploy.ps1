param (
    [string]$targetHost = $env:TALATG_DEPLOY_HOST,
    [string]$User = $env:TALATG_DEPLOY_USER,
    [string]$RemotePath = $env:TALATG_DEPLOY_PATH
)

if (-not $targetHost) { throw "Set TALATG_DEPLOY_HOST or pass -targetHost." }
if (-not $User) { throw "Set TALATG_DEPLOY_USER or pass -User." }
if (-not $RemotePath) { throw "Set TALATG_DEPLOY_PATH or pass -RemotePath." }

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { throw "ssh not found in PATH." }
if (-not (Get-Command scp -ErrorAction SilentlyContinue)) { throw "scp not found in PATH." }
if (-not (Get-Command tar -ErrorAction SilentlyContinue)) { throw "tar not found in PATH." }

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archiveName = "tala-bot-$timestamp.tar.gz"
$archivePath = Join-Path $PSScriptRoot $archiveName

Push-Location $root
try {
    $tarArgs = @(
        "-czf", $archivePath,
        "--exclude=.git",
        "--exclude=.env",
        "--exclude=data",
        "--exclude=sessions",
        "--exclude=ssh-mcp",
        "--exclude=*.tar.gz",
        "."
    )
    & tar @tarArgs
}
finally {
    Pop-Location
}

& scp $archivePath "$User@${targetHost}:/tmp/$archiveName"

$remoteCommand = "mkdir -p $RemotePath && tar -xzf /tmp/$archiveName -C $RemotePath --strip-components=1 && cd $RemotePath/deployment && docker compose up -d --build && rm /tmp/$archiveName"
& ssh "$User@$targetHost" $remoteCommand

Remove-Item $archivePath -Force
param(
    [Parameter(Mandatory=$true)][string]$Bundle,
    [Parameter(Mandatory=$true)][string]$Storage,
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$Bundle = (Resolve-Path $Bundle).Path
$Script = Join-Path $PSScriptRoot "../run_worker.py"
$Stdout = Join-Path $Bundle "worker.out"
$Stderr = Join-Path $Bundle "worker.err"
$Arguments = @("`"$Script`"", "--bundle", "`"$Bundle`"", "--storage", "`"$Storage`"")
$Process = Start-Process -FilePath $Python -ArgumentList $Arguments `
    -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr -PassThru
Write-Output "Started worker PID $($Process.Id). Logs: $Stdout and $Stderr"
Write-Output "Completion requires completed.json and matching imported checksums, not process exit alone."

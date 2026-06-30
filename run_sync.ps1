# Wrapper for Windows Task Scheduler.
# Runs the daily SFS sync and writes a timestamped log to .\logs\.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$logDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$stamp = Get-Date -Format "yyyy-MM-dd"
$logFile = Join-Path $logDir "sync_$stamp.log"

# Prefer a local virtual environment if present, else fall back to system python.
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPy) { $python = $venvPy } else { $python = "python" }

"=== Sync started $(Get-Date -Format o) ===" | Out-File -FilePath $logFile -Append -Encoding utf8
# Redirect via cmd so Python's stderr logging is captured as plain text. Doing
# `& $python ... *>> $logFile` makes PowerShell treat native stderr as an error
# which, under ErrorActionPreference=Stop, aborts the wrapper after the line
# above and reports a false failure.
cmd /c "`"$python`" run.py sync >> `"$logFile`" 2>&1"
$code = $LASTEXITCODE
"=== Sync finished $(Get-Date -Format o) exit=$code ===" | Out-File -FilePath $logFile -Append -Encoding utf8
exit $code

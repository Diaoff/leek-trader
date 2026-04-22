#Requires -Version 5.1

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RunDir = Join-Path $RootDir ".local\run"
$BackendPidFile = Join-Path $RunDir "backend.pid"
$FrontendPidFile = Join-Path $RunDir "frontend.pid"

function Stop-ProcessByPidFile {
    param([string]$Name, [string]$PidFile)

    if (-not (Test-Path $PidFile)) {
        Write-Host "$Name is not running."
        return
    }

    $pid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if (-not $pid -or -not (Get-Process -Id $pid -ErrorAction SilentlyContinue)) {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        Write-Host "$Name PID file was stale and has been cleaned up."
        return
    }

    Write-Host "Stopping $Name (PID $pid)..."
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue

    $attempts = 0
    while ($attempts -lt 10) {
        if (-not (Get-Process -Id $pid -ErrorAction SilentlyContinue)) {
            Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
            Write-Host "$Name stopped."
            return
        }
        Start-Sleep -Seconds 1
        $attempts++
    }

    Write-Host "$Name did not exit in time; forcing stop."
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

Stop-ProcessByPidFile "Frontend" $FrontendPidFile
Stop-ProcessByPidFile "Backend" $BackendPidFile

#Requires -Version 5.1

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RunDir = Join-Path $RootDir ".local\run"
$LogDir = Join-Path $RootDir ".local\logs"
$DataDir = Join-Path $RootDir ".local\data"
$BackendPidFile = Join-Path $RunDir "backend.pid"
$FrontendPidFile = Join-Path $RunDir "frontend.pid"
$BackendLogFile = Join-Path $LogDir "backend.log"
$FrontendLogFile = Join-Path $LogDir "frontend.log"
$FrontendUrlFile = Join-Path $RunDir "frontend.url"
$VenvDir = Join-Path $RootDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

$BackendHost = if ($env:BACKEND_HOST) { $env:BACKEND_HOST } else { "127.0.0.1" }
$BackendPort = if ($env:BACKEND_PORT) { [int]$env:BACKEND_PORT } else { 8000 }
$FrontendHost = if ($env:FRONTEND_HOST) { $env:FRONTEND_HOST } else { "127.0.0.1" }
$FrontendPort = if ($env:FRONTEND_PORT) { [int]$env:FRONTEND_PORT } else { 5173 }
$BackendUrl = if ($env:BACKEND_URL) { $env:BACKEND_URL } else { "http://${BackendHost}:${BackendPort}/" }
$FrontendUrl = if ($env:FRONTEND_URL) { $env:FRONTEND_URL } else { "" }

$SqlitePath = Join-Path $DataDir "leek_trader.db"
$BackendDatabaseUrl = if ($env:DATABASE_URL) { $env:DATABASE_URL } else { "sqlite:///${SqlitePath}" }
$BackendStartedByScript = $false
$FrontendStartedByScript = $false

New-Item -ItemType Directory -Force -Path $RunDir, $LogDir, $DataDir | Out-Null

function Cleanup-StartedProcesses {
    if ($FrontendStartedByScript -and (Test-Path $FrontendPidFile)) {
        $frontendPid = Get-Content $FrontendPidFile -ErrorAction SilentlyContinue
        if ($frontendPid -and (Get-Process -Id $frontendPid -ErrorAction SilentlyContinue)) {
            Stop-Process -Id $frontendPid -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $FrontendPidFile -Force -ErrorAction SilentlyContinue
    }

    if ($BackendStartedByScript -and (Test-Path $BackendPidFile)) {
        $backendPid = Get-Content $BackendPidFile -ErrorAction SilentlyContinue
        if ($backendPid -and (Get-Process -Id $backendPid -ErrorAction SilentlyContinue)) {
            Stop-Process -Id $backendPid -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $BackendPidFile -Force -ErrorAction SilentlyContinue
    }
}

function Is-Running {
    param([string]$PidFile)
    if (-not (Test-Path $PidFile)) { return $false }
    $pid = Get-Content $PidFile -ErrorAction SilentlyContinue
    return ($pid -and (Get-Process -Id $pid -ErrorAction SilentlyContinue))
}

function Cleanup-StalePid {
    param([string]$PidFile)
    if (Is-Running $PidFile) { return $true }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    return $false
}

function Ensure-PortAvailable {
    param([string]$Name, [string]$Host, [int]$Port, [string]$PidFile)
    Cleanup-StalePid $PidFile | Out-Null

    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($connection) {
        Write-Error "Error: $Name port ${Host}:${Port} is already in use."
        exit 1
    }
}

function Wait-ForUrl {
    param([string]$Name, [string]$Url, [int]$Timeout = 30)
    $elapsed = 0
    while ($elapsed -lt $Timeout) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -lt 500) { return $true }
        } catch { }
        Start-Sleep -Seconds 1
        $elapsed++
    }
    Write-Error "Error: $Name did not become ready within ${Timeout}s."
    return $false
}

function Wait-ForService {
    param([string]$Name, [string]$Url, [string]$PidFile, [string]$LogFile, [int]$Timeout = 30)
    $elapsed = 0
    while ($elapsed -lt $Timeout) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -lt 500) { return $true }
        } catch { }

        if (-not (Is-Running $PidFile)) {
            Write-Error "Error: $Name exited before becoming ready."
            if (Test-Path $LogFile) {
                Get-Content $LogFile -Tail 80 | Write-Error
            }
            return $false
        }

        Start-Sleep -Seconds 1
        $elapsed++
    }

    Write-Error "Error: $Name did not become ready within ${Timeout}s."
    if (Test-Path $LogFile) {
        Get-Content $LogFile -Tail 80 | Write-Error
    }
    return $false
}

function Resolve-FrontendUrl {
    param([int]$Timeout = 30)
    $elapsed = 0
    while ($elapsed -lt $Timeout) {
        if (Test-Path $FrontendLogFile) {
            $discoveredUrl = Select-String -Path $FrontendLogFile -Pattern "http://\S+" | Select-Object -Last 1 | ForEach-Object { $_.Matches[0].Value }
            if ($discoveredUrl) {
                $script:FrontendUrl = $discoveredUrl
                $discoveredUrl | Out-File -FilePath $FrontendUrlFile -Encoding utf8
                return $true
            }
        }

        if (-not (Is-Running $FrontendPidFile)) {
            Write-Error "Error: Frontend exited before reporting its URL."
            if (Test-Path $FrontendLogFile) {
                Get-Content $FrontendLogFile -Tail 80 | Write-Error
            }
            return $false
        }

        Start-Sleep -Seconds 1
        $elapsed++
    }

    Write-Error "Error: Frontend URL could not be determined from $FrontendLogFile within ${Timeout}s."
    if (Test-Path $FrontendLogFile) {
        Get-Content $FrontendLogFile -Tail 40 | Write-Error
    }
    return $false
}

function Ensure-BackendRuntime {
    if (-not (Test-Path $VenvPython)) {
        Write-Host "Creating Python virtual environment..."
        $venvResult = Start-Process -FilePath "python" -ArgumentList "-m venv $VenvDir" -NoNewWindow -Wait -PassThru
        if ($venvResult.ExitCode -ne 0) {
            Write-Error "Failed to create Python virtual environment."
            exit 1
        }
    }

    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $VenvPython
    $processInfo.Arguments = '-c "import uvicorn"'
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $processInfo
    $process.Start() | Out-Null
    $process.WaitForExit()

    if ($process.ExitCode -ne 0) {
        Write-Host "Installing backend dependencies..."
        $pipProcess = New-Object System.Diagnostics.ProcessStartInfo
        $pipProcess.FileName = $VenvPython
        $pipProcess.Arguments = "-m pip install -r $(Join-Path $RootDir 'backend\requirements.txt')"
        $pipProcess.UseShellExecute = $false
        $pipProcess.CreateNoWindow = $false

        $pip = New-Object System.Diagnostics.Process
        $pip.StartInfo = $pipProcess
        $pip.Start() | Out-Null
        $pip.WaitForExit()

        if ($pip.ExitCode -ne 0) {
            Write-Error "Failed to install backend dependencies."
            exit 1
        }
    }
}

function Ensure-FrontendRuntime {
    if (-not (Test-Path (Join-Path $RootDir "frontend\node_modules"))) {
        Write-Host "Installing frontend dependencies..."
        Push-Location (Join-Path $RootDir "frontend")
        npm install
        Pop-Location
    }
}

function Start-Backend {
    Ensure-PortAvailable "Backend" $BackendHost $BackendPort $BackendPidFile

    if (Is-Running $BackendPidFile) {
        $pid = Get-Content $BackendPidFile
        Write-Host "Backend is already running with PID $pid."
        return
    }

    Write-Host "Starting backend..."
    $null > $BackendLogFile

    $env:DATABASE_URL = $BackendDatabaseUrl
    $env:VITE_API_BASE_URL = if ($env:VITE_API_BASE_URL) { $env:VITE_API_BASE_URL } else { "http://${BackendHost}:${BackendPort}/api/v1" }
    $env:PYTHONPATH = Join-Path $RootDir "backend"

    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $VenvPython
    $processInfo.Arguments = "-m uvicorn app.main:app --host $BackendHost --port $BackendPort"
    $processInfo.WorkingDirectory = Join-Path $RootDir "backend"
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $processInfo
    $process.Start() | Out-Null
    $process.Id | Out-File -FilePath $BackendPidFile -Encoding utf8
    $script:BackendStartedByScript = $true

    Start-Sleep -Seconds 1
    if (-not (Is-Running $BackendPidFile)) {
        Write-Error "Error: Backend failed to start. Recent log output:"
        Get-Content $BackendLogFile -Tail 40 | Write-Error
        exit 1
    }
}

function Start-Frontend {
    if (Is-Running $FrontendPidFile) {
        $pid = Get-Content $FrontendPidFile
        Write-Host "Frontend is already running with PID $pid."
        if (Test-Path $FrontendUrlFile) {
            $script:FrontendUrl = Get-Content $FrontendUrlFile -Raw
        }
        return
    }

    Write-Host "Starting frontend..."
    $null > $FrontendLogFile
    Remove-Item $FrontendUrlFile -Force -ErrorAction SilentlyContinue

    Push-Location (Join-Path $RootDir "frontend")
    $env:VITE_API_BASE_URL = if ($env:VITE_API_BASE_URL) { $env:VITE_API_BASE_URL } else { "http://${BackendHost}:${BackendPort}/api/v1" }

    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = "cmd.exe"
    $processInfo.Arguments = "/c npm run dev -- --host $FrontendHost --port $FrontendPort"
    $processInfo.WorkingDirectory = (Join-Path $RootDir "frontend")
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $processInfo
    $process.Start() | Out-Null
    $process.Id | Out-File -FilePath $FrontendPidFile -Encoding utf8
    $script:FrontendStartedByScript = $true
    Pop-Location

    Start-Sleep -Seconds 1
    if (-not (Is-Running $FrontendPidFile)) {
        Write-Error "Error: Frontend failed to start. Recent log output:"
        Get-Content $FrontendLogFile -Tail 40 | Write-Error
        exit 1
    }
}

Ensure-BackendRuntime
Ensure-FrontendRuntime
Start-Backend
Start-Frontend

if (-not $FrontendUrl) {
    if (-not (Resolve-FrontendUrl 30)) {
        Cleanup-StartedProcesses
        exit 1
    }
}

if (-not (Wait-ForService "Backend" $BackendUrl $BackendPidFile $BackendLogFile 30)) {
    Cleanup-StartedProcesses
    exit 1
}

if (-not (Wait-ForService "Frontend" $FrontendUrl $FrontendPidFile $FrontendLogFile 30)) {
    Cleanup-StartedProcesses
    exit 1
}

Write-Host ""
Write-Host "Leek Trader local services are running." -ForegroundColor Green
Write-Host "Frontend: $FrontendUrl" -ForegroundColor Cyan
Write-Host "Backend:  http://${BackendHost}:${BackendPort}" -ForegroundColor Cyan
Write-Host "Database: $BackendDatabaseUrl" -ForegroundColor Gray
Write-Host "Logs:     $LogDir" -ForegroundColor Gray
Write-Host ""

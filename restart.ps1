#Requires -Version 5.1

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

$stopScript = Join-Path $RootDir "stop.ps1"
$startScript = Join-Path $RootDir "start.ps1"

& $stopScript
& $startScript

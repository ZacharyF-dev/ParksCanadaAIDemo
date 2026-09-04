$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Create the virtual environment and install dependencies first. See README.md."
}

& ".venv\Scripts\python.exe" run.py

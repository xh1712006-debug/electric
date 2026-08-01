$ErrorActionPreference = "Stop"

$PSScriptRoot = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition
$OcrProjectRoot = Join-Path $PSScriptRoot "..\OCR_PRJ"

Write-Host "Setting up OCR_PRJ environment at $OcrProjectRoot..." -ForegroundColor Cyan

if (-not (Test-Path $OcrProjectRoot)) {
    Write-Host "Error: OCR_PRJ directory not found at $OcrProjectRoot" -ForegroundColor Red
    exit 1
}

Set-Location $OcrProjectRoot

Write-Host "Running OCR setup script..."
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_debug_ui.ps1

Write-Host "OCR_PRJ setup completed successfully." -ForegroundColor Green

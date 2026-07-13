# Stop stale listeners on ports 8000-8010, then start the scraper web UI.
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path $PSScriptRoot -Parent
8000..8010 | ForEach-Object {
    Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "Stopping PID $($_.OwningProcess) on port $_..."
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 2
Set-Location $root
Write-Host "Starting spaider_crawler on http://127.0.0.1:8000 ..."
python app.py
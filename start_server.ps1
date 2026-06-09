# OntoBridge shared server startup script
# Usage:
#   .\start_server.ps1              # persistent SQLite, builds frontend
#   .\start_server.ps1 -NoBuild     # skip npm build (already built)
#   .\start_server.ps1 -Port 8080   # custom port
#   .\start_server.ps1 -Demo        # in-memory mode (resets on restart)

param(
    [switch]$NoBuild,
    [switch]$Demo,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# --- 1. Build frontend ---
if (-not $NoBuild) {
    Write-Host "Building React frontend..." -ForegroundColor Cyan
    Push-Location "$root\frontend"
    try {
        npm run build
        if (-not $?) { throw "npm build failed" }
    } finally {
        Pop-Location
    }
    Write-Host "Frontend built." -ForegroundColor Green
}

# --- 2. Detect local IP ---
$localIp = (
    Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.*" } |
    Select-Object -First 1
).IPAddress

# --- 3. Set environment ---
if (-not $Demo) {
    $env:DB_PATH = "$root\ontobridge.db"
    Write-Host "Storage: SQLite  ($($env:DB_PATH))" -ForegroundColor Cyan
} else {
    Remove-Item Env:\DB_PATH -ErrorAction SilentlyContinue
    Write-Host "Storage: in-memory (demo mode)" -ForegroundColor Yellow
}

# CORS: allow all — teammates connect from different IPs
$env:CORS_ORIGINS = ""

# --- Dawiso integration (optional) ---
# Configure Dawiso through .env (loaded automatically at startup):
#   DAWISO_URL, DAWISO_JWT, DAWISO_SESSION_ID, DAWISO_SPACE_ID, DAWISO_APP_ID
# jwt and session_id are browser-session cookies — keep them in .env, never commit them.
# See .env.example. Leave unset to disable Dawiso publishing.

# --- 4. Print access info ---
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  OntoBridge starting on port $Port"     -ForegroundColor Green
Write-Host ""
Write-Host "  This machine:  http://localhost:$Port"
if ($localIp) {
    Write-Host "  Team members:  http://${localIp}:$Port" -ForegroundColor Yellow
}
Write-Host "  API docs:      http://localhost:$Port/docs"
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# --- 5. Start uvicorn ---
Push-Location $root
python -m uvicorn api_server:app --host 0.0.0.0 --port $Port
Pop-Location

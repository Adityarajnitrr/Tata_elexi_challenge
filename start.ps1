# One-command startup script for Battery Pack Design Platform (Backend + Frontend)
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Starting Battery Pack Design Platform & ML Engine" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Check if model exists, if not generate data and train
if (-not (Test-Path "models\battery_pack_model.joblib")) {
    Write-Host "[1/3] Generating synthetic physics dataset..." -ForegroundColor Yellow
    python -m ml.generate_data
    Write-Host "[2/3] Training surrogate models..." -ForegroundColor Yellow
    python -m ml.train
} else {
    Write-Host "[✓] ML model artifact verified in models\battery_pack_model.joblib" -ForegroundColor Green
}

Write-Host "[3/3] Launching FastAPI backend server on http://localhost:8000..." -ForegroundColor Green
Start-Process python -ArgumentList "-m uvicorn backend.main:app --host 0.0.0.0 --port 8000"

Start-Sleep -Seconds 2
Write-Host "Opening web application in default browser..." -ForegroundColor Cyan
Start-Process "index.html"
Write-Host "Platform is running! Press Ctrl+C in backend console to exit." -ForegroundColor Green

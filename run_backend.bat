@echo off
echo ========================================================
echo Starting Battery Pack Design Platform ML Backend
echo ========================================================
echo Activating Python environment and launching FastAPI...
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pause

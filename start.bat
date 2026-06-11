@echo off
chcp 65001 >nul
title WeChat AI Bot v4

echo ==========================================
echo   WeChat AI Bot v4
echo ==========================================
echo.

echo [1/3] Checking dependencies...
pip install -r requirements.txt --quiet 2>nul
if %errorlevel% neq 0 (
    echo [WARN] Some dependencies may be missing
)

echo [2/3] Starting bot...
echo.
echo   Web UI will open at http://localhost:7860
echo   Press Ctrl+C in this window to stop
echo.

python app.py

pause

@echo off
chcp 65001 >nul
title WeChat AI Bot

cd /d "%~dp0"

echo ==========================================
echo   WeChat AI Bot
echo ==========================================
echo.

:: 检查 .env
if not exist ".env" (
    echo [ERROR] 未找到 .env 文件！
    echo   请先运行 setup.bat 进行初始化
    pause
    exit /b 1
)

:: 使用虚拟环境
if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
    echo [OK] 使用项目虚拟环境
) else (
    set PYTHON=python
    echo [WARN] 未找到虚拟环境，使用系统 Python
    echo   建议先运行 setup.bat
)

echo.
echo   Web UI: http://localhost:7860
echo   按 Ctrl+C 停止
echo.

%PYTHON% app.py

pause

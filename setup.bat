@echo off
chcp 65001 >nul
title WeChat AI Bot - 初始化安装

echo ==========================================
echo   WeChat AI Bot - 一键安装
echo ==========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 未找到 Python！请先安装 Python 3.10+
    echo   下载: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python 已检测到
echo.

:: 创建虚拟环境
if not exist "venv" (
    echo [1/3] 创建虚拟环境...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [OK] 虚拟环境已创建
) else (
    echo [1/3] 虚拟环境已存在，跳过创建
)

:: 激活虚拟环境并安装依赖
echo.
echo [2/3] 安装依赖...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [WARN] 部分依赖安装失败，PaddleOCR 可能需要 Python 3.8-3.12
    echo        OCR 功能会自动回退到 RapidOCR，不影响使用
)
echo [OK] 依赖安装完成

:: 复制 .env 模板
echo.
echo [3/3] 配置环境变量...
if not exist ".env" (
    copy .env.example .env >nul
    echo [OK] 已创建 .env 文件，请编辑填入你的 API Key
    echo.
    echo   请用记事本打开 .env 文件，修改 LLM_API_KEY
    echo   获取免费 API Key: https://platform.deepseek.com/
) else (
    echo [OK] .env 已存在，跳过
)

echo.
echo ==========================================
echo   安装完成！
echo ==========================================
echo.
echo   下一步:
echo   1. 编辑 .env 文件，填入 LLM_API_KEY
echo   2. 登录你的微信电脑版
echo   3. 双击 start.bat 启动
echo.
echo   推荐: 用 Windows Sandbox 隔离运行 (见 GUIDE.md)
echo.
pause

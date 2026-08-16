@echo off
chcp 65001 >nul
title PDF 工具包

echo ========================================
echo   PDF 工具包 - 快速启动
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [✗] 未检测到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)
echo [✓] Python 已就绪

:: 安装依赖（如需要）
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo [!] 正在安装依赖...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [✗] 依赖安装失败
        pause
        exit /b 1
    )
) else (
    echo [✓] 依赖已就绪
)

echo.
echo [✓] 启动服务，浏览器打开 http://localhost:8001
echo     按 Ctrl+C 停止服务
echo ========================================
echo.

python run.py --host 127.0.0.1 --port 8001

pause

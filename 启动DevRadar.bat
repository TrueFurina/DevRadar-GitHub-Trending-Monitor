@echo off
chcp 65001 >nul
title DevRadar — GitHub 热门项目追踪器

echo ============================================
echo   DevRadar 正在启动...
echo ============================================
echo.

:: 切换到脚本所在目录
cd /d "%~dp0"

:: 检查 Python 是否可用
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 检查依赖是否安装
python -c "import PyQt6" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 首次运行，正在安装依赖...
    pip install -r requirements.txt
    echo.
)

:: 以后台方式启动 GUI (不显示控制台窗口)
start "" pythonw run.py

:: 等待几秒后检查是否启动成功
timeout /t 3 /nobreak >nul

echo.
echo ✅ DevRadar 已启动！
echo    GUI 窗口应该已经出现在桌面上。
echo    如果未显示，请检查任务栏托盘图标。
echo.
echo    关闭 GUI 窗口即可退出程序。
echo.
echo ============================================
pause

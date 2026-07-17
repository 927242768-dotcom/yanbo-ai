@echo off
chcp 65001 >nul
cd /d "%~dp0"
python configure_auto_start.py
if errorlevel 1 (
  echo.
  echo 设置自启动失败，请查看上方提示。
  pause
  exit /b 1
)
echo.
echo 已完成，以后登录Windows后会自动在后台启动彦博公网服务。
pause

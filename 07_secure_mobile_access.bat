@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动彦博公网手机服务...
echo 启动后手机可使用移动数据、其他Wi-Fi或异地网络连接。
echo.
python secure_mobile_access.py
if errorlevel 1 echo 启动失败，请查看上方提示。
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动彦博手机服务...
echo 手机和电脑需要连接同一个 Wi-Fi。
python web_chat.py --host 0.0.0.0 --port 7860
pause

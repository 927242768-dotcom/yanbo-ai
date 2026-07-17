@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/3] 正在检查并安装依赖...
python -m pip install -r requirements.txt
if errorlevel 1 goto error
echo.
echo [2/3] 正在准备兼容模型...
python download_model.py
if errorlevel 1 goto error
echo.
echo [3/3] 正在构建当前彦博版本...
python release_model.py
if errorlevel 1 goto error
echo.
echo 彦博初始化完成，已包含图片文字识别组件。
pause
exit /b 0
:error
echo.
echo 初始化失败，请查看上方错误信息。
pause
exit /b 1

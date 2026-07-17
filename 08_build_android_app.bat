@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在构建彦博 AI Android 正式安装包...
python mobile_app\tools\build_android_release.py --with-aab --clean
if errorlevel 1 goto error
echo.
echo 构建完成，安装包位于 releases 文件夹。
pause
exit /b 0
:error
echo.
echo 构建失败，请查看上方错误。
pause
exit /b 1

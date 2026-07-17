@echo off
chcp 65001 >nul
cd /d "%~dp0mobile_app"
set "NPM=npm"
set "NPX=npx"
where npm >nul 2>&1
if errorlevel 1 set "NPM=D:\manim\数据结构\.toolchain\node-v22.19.0-win-x64\npm.cmd"
where npx >nul 2>&1
if errorlevel 1 set "NPX=D:\manim\数据结构\.toolchain\node-v22.19.0-win-x64\npx.cmd"
echo [1/4] 安装手机应用依赖...
call "%NPM%" install
if errorlevel 1 goto error
echo [2/4] 生成 Android 工程...
if not exist android call "%NPX%" cap add android
if errorlevel 1 goto error
echo [3/4] 生成 iOS 工程...
if not exist ios call "%NPX%" cap add ios
if errorlevel 1 echo iOS工程生成失败，可稍后在Mac上执行 npx cap add ios。
echo [4/4] 同步网页资源...
call "%NPX%" cap sync
if errorlevel 1 goto error
echo 正在应用彦博Android兼容补丁...
python tools\patch_android_project.py
if errorlevel 1 goto error
echo.
echo 手机应用工程准备完成。
echo Android工程：mobile_app\android
echo iOS工程：mobile_app\ios
pause
exit /b 0
:error
echo.
echo 准备失败，请查看上方错误。
pause
exit /b 1

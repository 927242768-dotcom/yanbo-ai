@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在清理彦博项目缓存和临时构建文件...

for /d /r %%D in (__pycache__) do @if exist "%%D" rmdir /s /q "%%D"
if exist ".devspace-computer" rmdir /s /q ".devspace-computer"
if exist "mobile\icon.svg" del /f /q "mobile\icon.svg"
for %%F in ("releases\*.png") do if /I not "%%~nxF"=="彦博手机访问二维码.png" del /f /q "%%~fF"
if exist "mobile_app\android\.gradle" rmdir /s /q "mobile_app\android\.gradle"
if exist "mobile_app\android\app\build" rmdir /s /q "mobile_app\android\app\build"
if exist "mobile_app\android\build" rmdir /s /q "mobile_app\android\build"
if exist "mobile_app\android\capacitor-cordova-android-plugins\build" rmdir /s /q "mobile_app\android\capacitor-cordova-android-plugins\build"
if exist "mobile_app\node_modules\@capacitor\android\capacitor\build" rmdir /s /q "mobile_app\node_modules\@capacitor\android\capacitor\build"

echo 清理完成。模型、训练断点、签名、源码和 releases 发布包均已保留。
pause

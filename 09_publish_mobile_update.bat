@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在快速发布彦博 AI Android 新版本...
echo 默认自动增加最后一位版本号，例如 1.0.0 -^> 1.0.1。
echo 本流程使用增量构建，只生成可直接更新的APK，速度明显更快。
echo 如需同时生成AAB和iOS完整发布包，请在命令行添加 --full。
python mobile_app\tools\publish_mobile_update.py
if errorlevel 1 goto error
echo.
echo 发布完成。新APK位于 releases 文件夹，旧版本会自动提示更新。
pause
exit /b 0
:error
echo.
echo 发布失败，请查看上方错误。
pause
exit /b 1

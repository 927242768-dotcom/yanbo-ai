@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动彦博长期训练流程...
echo 本轮会生成新题、加入导师样本、从现有断点继续训练并自动评估。
echo.
python train_yanbo.py --steps 80 --teacher-count 8 --max-length 320
if errorlevel 1 goto error
echo.
echo 本轮训练完成。以后再次双击本文件，会自动进入下一轮并继续训练。
pause
exit /b 0
:error
echo.
echo 训练失败，请查看上方错误信息。已保存的训练检查点不会丢失。
pause
exit /b 1

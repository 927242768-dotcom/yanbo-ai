@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动彦博深度训练...
echo 本轮将生成更多导师样本，并追加400个训练步骤。
echo 在CPU电脑上可能运行较长时间，请保持电脑通电并避免中途关机。
echo 训练会定期保存检查点，中断后再次运行可继续。
echo.
python train_yanbo.py --steps 400 --teacher-count 20 --max-length 384 --learning-rate 1e-5
if errorlevel 1 goto error
echo.
echo 深度训练完成。
pause
exit /b 0
:error
echo.
echo 深度训练中断或失败。已保存的检查点不会丢失，再次运行可继续。
pause
exit /b 1

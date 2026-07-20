@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  echo 请把PDF、Word、图片、文本或代码文件/文件夹拖到这个BAT上。
  echo 也可以在命令行运行：13_import_knowledge.bat "D:\资料文件夹"
  pause
  exit /b 1
)
python import_knowledge.py %*
if errorlevel 1 (
  echo.
  echo 资料导入未完整完成，请查看上方提示。
  pause
  exit /b 1
)
echo.
echo 资料已加入彦博本地知识库。
pause

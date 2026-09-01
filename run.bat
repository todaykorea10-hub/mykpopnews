@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================
echo   K-CHART NEWS Auto Publisher
echo   (Closing this window stops the script. Ctrl+C to stop safely)
echo ============================================
echo.

python auto_publish.py

echo.
echo ============================================
echo   Program has stopped.
echo   Please check for error messages above.
echo ============================================
pause

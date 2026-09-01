@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================
echo   Replacing Existing Post Images
echo   (Photos to Typography Cards)
echo ============================================
echo.

python regenerate_images.py

echo.
echo ============================================
echo   Run finished. Please check for errors above.
echo ============================================
pause

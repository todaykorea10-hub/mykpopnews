@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================
echo   Uploading Group Images (one-time per file)
echo ============================================
echo.

python upload_group_images.py

echo.
echo ============================================
echo   Run finished. Please check for errors above.
echo ============================================
pause

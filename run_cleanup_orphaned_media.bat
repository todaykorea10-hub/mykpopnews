@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================
echo   Cleaning Up Orphaned Media Files
echo   (Check config.py DRY_RUN setting first)
echo ============================================
echo.

python cleanup_orphaned_media.py

echo.
echo ============================================
echo   Run finished. Please check for errors above.
echo ============================================
pause

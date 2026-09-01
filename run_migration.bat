@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================
echo   Blogger to WordPress Migration
echo ============================================
echo.

python migrate_from_blogger.py

echo.
echo ============================================
echo   Migration run finished.
echo   Please check for error messages above.
echo ============================================
pause

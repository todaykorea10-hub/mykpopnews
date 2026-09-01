@echo off
cd /d "%~dp0"

REM Register this file in Windows Task Scheduler to run silently
REM (no window) on a schedule. Output is appended to run_log.txt.
REM Use this together with RUN_CONTINUOUSLY = False in config.py.

REM --- Log rotation: if run_log.txt exceeds ~5MB, archive it so it never grows forever ---
if exist run_log.txt (
    for %%A in (run_log.txt) do set logsize=%%~zA
    if defined logsize (
        if %logsize% GTR 5242880 (
            if exist run_log_old.txt del run_log_old.txt
            ren run_log.txt run_log_old.txt
        )
    )
)

echo [%date% %time%] Run started >> run_log.txt
python auto_publish.py >> run_log.txt 2>&1
echo [%date% %time%] Run finished >> run_log.txt
echo. >> run_log.txt

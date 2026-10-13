@echo off
REM Windows Task Scheduler setup for daily GPR data updates
REM Run this batch file as Administrator to set up the daily task

echo Setting up daily GPR data update task...

REM Get the current directory
set SCRIPT_DIR=%~dp0
set PYTHON_SCRIPT=%SCRIPT_DIR%daily_update.py
set WORK_DIR=%SCRIPT_DIR%

echo Script directory: %SCRIPT_DIR%
echo Python script: %PYTHON_SCRIPT%
echo Working directory: %WORK_DIR%

REM Create the scheduled task with working directory set
schtasks /create ^
    /tn "GPR_Daily_Update" ^
    /tr "cmd /c cd /d \"%WORK_DIR%\" && python \"%PYTHON_SCRIPT%\"" ^
    /sc daily ^
    /st 06:00 ^
    /sd %date% ^
    /f

if %errorlevel% == 0 (
    echo Task created successfully!
    echo The GPR dataset will be updated daily at 6:00 AM
    echo.
    echo To check the task status, run: schtasks /query /tn "GPR_Daily_Update"
    echo To delete the task, run: schtasks /delete /tn "GPR_Daily_Update" /f
) else (
    echo Failed to create task. Make sure you run this as Administrator.
)

pause

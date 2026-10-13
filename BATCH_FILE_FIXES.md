# Setup Daily Update - Issues and Fixes

## ❌ Problems with Current setup_daily_update.bat

### 1. **WRONG PATH TO PYTHON SCRIPT** (Critical Issue)
**Current Line:**
```batch
set PYTHON_SCRIPT=%SCRIPT_DIR%daily_update.py
```

**Problem:** Points to `daily_update.py` in root, but the actual working script is in `app\daily_update.py`

**Fix:**
```batch
set PYTHON_SCRIPT=%SCRIPT_DIR%app\daily_update.py
```

---

### 2. **NO PYTHON VALIDATION**
**Problem:** Doesn't check if Python is installed before creating the task

**Fix:** Add before creating the task:
```batch
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found in PATH.
    pause
    exit /b 1
)
```

---

### 3. **DATE FORMAT ISSUES**
**Current Line:**
```batch
/sd %date%
```

**Problem:** `%date%` format varies by system locale (US: MM/DD/YYYY, India: DD-MM-YYYY, etc.)

**Fix:**
```batch
REM Get date in YYYY-MM-DD format
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set START_DATE=%datetime:~0,4%-%datetime:~4,2%-%datetime:~6,2%
```
Then use:
```batch
/sd %START_DATE%
```

---

### 4. **NO FULL PYTHON PATH**
**Current Line:**
```batch
/tr "python \"%PYTHON_SCRIPT%\""
```

**Problem:** Uses `python` command which may not work if Python isn't in PATH when Task Scheduler runs

**Fix:**
```batch
REM Get full path to Python
for /f "delims=" %%i in ('where python') do set PYTHON_PATH=%%i

REM Then use in schtasks:
/tr "\"%PYTHON_PATH%\" \"%PYTHON_SCRIPT%\""
```

---

### 5. **NO FILE EXISTENCE CHECK**
**Problem:** Doesn't verify the Python script exists before creating the task

**Fix:** Add after setting paths:
```batch
if not exist "%PYTHON_SCRIPT%" (
    echo ERROR: Python script not found at %PYTHON_SCRIPT%
    pause
    exit /b 1
)
```

---

### 6. **NO WORKING DIRECTORY**
**Problem:** Script may not run from correct directory, causing import errors

**Note:** The script imports from `main.py` which is in the `app` folder. The task should have its working directory set to the `app` folder.

**Unfortunately, schtasks.exe doesn't support `/dir` parameter directly.** 

**Workaround Options:**

**Option A:** Modify the task command to include `cd`:
```batch
/tr "cmd /c cd /d \"%WORK_DIR%\" && \"%PYTHON_PATH%\" daily_update.py"
```

**Option B:** After creating the task, manually edit it in Task Scheduler GUI to set "Start in" directory

**Option C:** Create a wrapper batch file in the app folder

---

## ✅ COMPLETE FIXED VERSION

Here's the complete corrected batch file content:

```batch
@echo off
REM Windows Task Scheduler setup for daily GPR data updates
REM Run this batch file as Administrator to set up the daily task

echo =========================================
echo GPR Daily Update - Task Scheduler Setup
echo =========================================
echo.

REM Get the current directory
set SCRIPT_DIR=%~dp0
set PYTHON_SCRIPT=%SCRIPT_DIR%app\daily_update.py
set WORK_DIR=%SCRIPT_DIR%app

echo Script directory: %SCRIPT_DIR%
echo Python script: %PYTHON_SCRIPT%
echo Working directory: %WORK_DIR%
echo.

REM Verify Python script exists
if not exist "%PYTHON_SCRIPT%" (
    echo ERROR: Python script not found at:
    echo %PYTHON_SCRIPT%
    pause
    exit /b 1
)
echo [OK] Python script found

REM Find Python executable
echo Searching for Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found in PATH.
    pause
    exit /b 1
)

REM Get full path to Python
for /f "delims=" %%i in ('where python') do set PYTHON_PATH=%%i
echo [OK] Found Python at: %PYTHON_PATH%
echo.

REM Get current date in YYYY-MM-DD format
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set START_DATE=%datetime:~0,4%-%datetime:~4,2%-%datetime:~6,2%

echo Creating scheduled task...
echo   Task: GPR_Daily_Update
echo   Schedule: Daily at 6:00 AM
echo   Start Date: %START_DATE%
echo.

REM Create the scheduled task
schtasks /create ^
    /tn "GPR_Daily_Update" ^
    /tr "cmd /c cd /d \"%WORK_DIR%\" && \"%PYTHON_PATH%\" daily_update.py" ^
    /sc daily ^
    /st 06:00 ^
    /sd %START_DATE% ^
    /rl HIGHEST ^
    /f

if %errorlevel% == 0 (
    echo.
    echo ========================================
    echo SUCCESS! Task created successfully!
    echo ========================================
    echo.
    echo Commands:
    echo   Test run:    schtasks /run /tn "GPR_Daily_Update"
    echo   Check task:  schtasks /query /tn "GPR_Daily_Update"
    echo   Delete task: schtasks /delete /tn "GPR_Daily_Update" /f
    echo.
) else (
    echo.
    echo ERROR: Failed to create task
    echo Make sure you run this as Administrator.
    echo.
)

pause
```

---

## 📋 Answer: Do You Need to Install a Scheduler?

### NO - Windows Task Scheduler is Built-in! ✅

**Key Points:**

1. **Cron is for Linux/Unix** - Not available on Windows
2. **Windows Task Scheduler** - Built into Windows, already available
3. **No installation needed** - Already on your system
4. **Access it via:**
   - Command: `taskschd.msc` (Win + R)
   - Command: `schtasks` command-line tool
   - Control Panel → Administrative Tools → Task Scheduler

### The batch file CREATES the scheduled task automatically

The `schtasks /create` command in the batch file does everything for you - it talks to Windows Task Scheduler and sets up the job.

---

## 🧪 How to Test the Fix

### Step 1: Update the batch file
Copy the complete fixed version above into your `setup_daily_update.bat`

### Step 2: Run as Administrator
Right-click `setup_daily_update.bat` → "Run as Administrator"

### Step 3: Verify
```cmd
schtasks /query /tn "GPR_Daily_Update"
```

### Step 4: Test run
```cmd
schtasks /run /tn "GPR_Daily_Update"
```

### Step 5: Check logs
Look for `app\gpr_update.log` file

---

## 🔧 Alternative: Manual Setup in Task Scheduler GUI

If the batch file still doesn't work:

1. Press `Win + R`, type `taskschd.msc`, press Enter
2. Click "Create Basic Task"
3. Name: `GPR_Daily_Update`
4. Trigger: Daily, 6:00 AM
5. Action: Start a program
   - **Program**: Full path to python.exe
   - **Arguments**: Full path to `app\daily_update.py`
   - **Start in**: `d:\price-prediction-service-main\price-prediction-service-main\app`
6. Finish and test

---

## 📞 Quick Diagnosis Commands

```cmd
REM Check if Python is accessible
where python

REM Check if task exists
schtasks /query /tn "GPR_Daily_Update"

REM View task details
schtasks /query /tn "GPR_Daily_Update" /fo LIST /v

REM Test run the script manually
cd app
python daily_update.py

REM Check last run time
schtasks /query /tn "GPR_Daily_Update" /fo LIST /v | findstr "Last Run"
```

---

## 🎯 Summary

**Main Issues:**
1. ❌ Wrong path (pointing to root instead of app folder)
2. ❌ No Python validation
3. ❌ Date format problems
4. ❌ No working directory specification

**Solution:**
- ✅ Update batch file with fixes above
- ✅ Windows Task Scheduler is already installed
- ✅ No additional software needed
- ✅ Run batch file as Administrator

**Scheduler Question:**
- Windows Task Scheduler is built-in (no installation needed)
- The batch file creates the scheduled task automatically
- Cron is not available on Windows (it's for Linux)

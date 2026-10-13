# Daily Update Scheduler Setup Guide

## Important: Windows Task Scheduler vs Cron

**Your system uses Windows**, which means:
- ❌ **Cron is NOT available** (Cron is for Linux/Unix systems)
- ✅ **Windows Task Scheduler is built-in** and already available
- ✅ No additional software installation needed

## Issues Found in Current setup_daily_update.bat

1. **Wrong Python script path**: Points to `daily_update.py` but should point to `app\daily_update.py`
2. **Python not found**: Doesn't verify Python is installed or accessible
3. **Date format issues**: Uses `%date%` which varies by system locale
4. **No working directory**: Task doesn't specify where to run from
5. **No validation**: Doesn't check if files exist before creating task

## Solution: Fixed Batch File

The fixed version includes:
- ✅ Correct path to `app\daily_update.py`
- ✅ Python executable detection
- ✅ File existence validation
- ✅ Proper date formatting
- ✅ Working directory specification
- ✅ Better error messages
- ✅ Test run option

## How to Use Windows Task Scheduler

### Option 1: Use the Fixed Batch File (Recommended)

1. **Run as Administrator**:
   - Right-click on `setup_daily_update_FIXED.bat`
   - Select "Run as Administrator"
   - Follow the prompts

2. **Verify Task Creation**:
   ```cmd
   schtasks /query /tn "GPR_Daily_Update"
   ```

3. **Test Run Manually**:
   ```cmd
   schtasks /run /tn "GPR_Daily_Update"
   ```

4. **Check Logs**:
   - Look for `gpr_update.log` in the project directory
   - Check for any errors

### Option 2: Manual Task Scheduler Setup

If the batch file doesn't work, you can set up the task manually:

1. **Open Task Scheduler**:
   - Press `Win + R`
   - Type `taskschd.msc`
   - Press Enter

2. **Create New Task**:
   - Click "Create Basic Task" in the right panel
   - Name: `GPR_Daily_Update`
   - Description: `Daily GPR dataset update`

3. **Set Trigger**:
   - Trigger: Daily
   - Start: Today
   - Time: 06:00 AM
   - Recur every: 1 day

4. **Set Action**:
   - Action: Start a program
   - Program/script: Full path to python.exe (e.g., `C:\Python39\python.exe`)
   - Add arguments: Full path to script (e.g., `"d:\price-prediction-service-main\price-prediction-service-main\app\daily_update.py"`)
   - Start in: `d:\price-prediction-service-main\price-prediction-service-main\app`

5. **Set Conditions**:
   - Uncheck "Start the task only if the computer is on AC power"
   - Check "Wake the computer to run this task" (optional)

6. **Finish and Test**:
   - Save the task
   - Right-click on the task → Run
   - Check the log file

## Troubleshooting

### Problem: "Python not found"
**Solution**: 
```cmd
where python
```
If no result, install Python or add it to PATH.

### Problem: "Access Denied"
**Solution**: Run the batch file as Administrator.

### Problem: Task runs but script fails
**Solution**: 
1. Check `gpr_update.log` for errors
2. Verify all dependencies are installed:
   ```cmd
   pip install -r requirements.txt
   ```
3. Ensure `.env` files are configured correctly

### Problem: Date format error
**Solution**: Use the fixed batch file which handles dates properly.

### Problem: Import errors in script
**Solution**: 
- The script tries to import from `main.py` in the `app` folder
- Make sure working directory is set to the `app` folder
- Or use the fixed batch file which handles this

## Checking Task Status

### View Task Details:
```cmd
schtasks /query /tn "GPR_Daily_Update" /fo LIST /v
```

### View Last Run Result:
```cmd
schtasks /query /tn "GPR_Daily_Update" /fo LIST /v | findstr "Last Run"
```

### Delete Task (if needed):
```cmd
schtasks /delete /tn "GPR_Daily_Update" /f
```

## Alternative: Using Python Script Directly

If Task Scheduler doesn't work for your needs, you can also:

### Option A: Run manually when needed
```cmd
cd app
python daily_update.py
```

### Option B: Use the API endpoint
Your FastAPI service has a manual update endpoint:
```
GET http://localhost:8000/data/update
```

You can call this from:
- A web browser
- PowerShell: `Invoke-WebRequest -Uri "http://localhost:8000/data/update"`
- Curl: `curl http://localhost:8000/data/update`

## Logs Location

The daily update script creates a log file:
- **File**: `gpr_update.log`
- **Location**: Same directory as the script
- **Contains**: Update status, errors, timestamps

## Testing the Setup

1. **Delete old task** (if exists):
   ```cmd
   schtasks /delete /tn "GPR_Daily_Update" /f
   ```

2. **Run the fixed batch file as Administrator**

3. **Verify task exists**:
   ```cmd
   schtasks /query /tn "GPR_Daily_Update"
   ```

4. **Test run immediately**:
   ```cmd
   schtasks /run /tn "GPR_Daily_Update"
   ```

5. **Check the log**:
   ```cmd
   type gpr_update.log
   ```

## Summary

- ✅ Windows Task Scheduler is built-in (no installation needed)
- ✅ Use the fixed batch file to set up the task
- ✅ Run as Administrator
- ✅ Check logs for verification
- ✅ Manual API endpoint available as backup

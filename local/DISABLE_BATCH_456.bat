@echo off
setlocal
cd /d "%~dp0"
if exist BATCH_456_TESTED.json move /Y BATCH_456_TESTED.json BATCH_456_TESTED.disabled.json >nul
echo Batch disabled on next Bridge restart. Existing services not stopped.
pause

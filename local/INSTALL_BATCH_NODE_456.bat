@echo off
setlocal
set "TARGET=%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Installs\Caratzon-3D\ComfyUI\custom_nodes"
if not exist "%TARGET%\" (
  echo ComfyUI custom_nodes directory not found. No changes made.
  pause
  exit /b 1
)
if not exist "%~dp0comfy_nodes456\__init__.py" (
  echo Missing update file. Copy the local folder from ZIP first.
  pause
  exit /b 1
)
if not exist "%TARGET%\caratzon_batch456\" mkdir "%TARGET%\caratzon_batch456"
if exist "%TARGET%\caratzon_batch456\__init__.py" copy /Y "%TARGET%\caratzon_batch456\__init__.py" "%TARGET%\caratzon_batch456\__init__.py.bak" >nul
copy /Y "%~dp0comfy_nodes456\__init__.py" "%TARGET%\caratzon_batch456\__init__.py"
if errorlevel 1 exit /b 1
echo Installed experimental batch node. Restart ComfyUI before testing. No batch enabled yet.
pause

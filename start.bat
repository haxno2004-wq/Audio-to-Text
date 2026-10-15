@echo off
setlocal
cd /d "%~dp0"

python --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python was not found. Install it with:
  echo     winget install -e --id Python.Python.3.12
  echo Then close this window and run start.bat again.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating a private Python environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Could not create the environment.
    pause
    exit /b 1
  )
)

if not exist ".venv\.installed" (
  echo Installing packages. This takes a few minutes the first time...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Package install failed. Check your internet connection and run start.bat again.
    pause
    exit /b 1
  )
  echo ok> ".venv\.installed"
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo.
  echo A settings file was created. Paste your DEEPGRAM_API_KEY and ASSEMBLYAI_API_KEY,
  echo save, and close Notepad to continue.
  notepad ".env"
)

echo.
echo Starting on http://localhost:8080  -  close this window or press Ctrl+C to stop.
".venv\Scripts\python.exe" run.py
pause

@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\activate" (
  echo Please run setup.bat first.
  exit /b 1
)

call .venv\Scripts\activate

if exist "bin\ffmpeg.exe" (
  rem Local ffmpeg bulundu
) else (
  where ffmpeg >nul 2>&1
  if not %errorlevel%==0 (
    echo Warning: ffmpeg not found.
  )
)

python -m dje

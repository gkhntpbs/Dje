@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\activate" (
  where py >nul 2>&1
  if %errorlevel%==0 (
    set "PYEXE=py -3"
  ) else (
    set "PYEXE=python"
  )
  %PYEXE% -m venv .venv
  echo Virtual environment created.
)

call .venv\Scripts\activate

python -m pip install --upgrade pip

if exist "requirements.txt" (
  pip install -r requirements.txt
  echo Dependencies installed from requirements.txt.
) else if exist "pyproject.toml" (
  pip install -e .
  echo Dependencies installed from pyproject.toml (pip install -e .).
) else (
  echo Dependency file not found.
  exit /b 1
)

echo Setup completed.

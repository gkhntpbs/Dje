@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "BIN_DIR=%CD%\bin"
set "DOWNLOADS_DIR=%CD%\downloads"

if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"
if not exist "%DOWNLOADS_DIR%" mkdir "%DOWNLOADS_DIR%"

echo.
echo ========================================
echo       Dje Setup - Windows Install
echo ========================================
echo.

call :install_ffmpeg
if errorlevel 1 goto :setup_failed

call :install_opus
if errorlevel 1 goto :setup_failed

call :ensure_virtualenv
if errorlevel 1 goto :setup_failed

call :install_python_deps
if errorlevel 1 goto :setup_failed

call :show_summary
goto :eof

:: ----------------------------
:: FFmpeg Installation
:: ----------------------------
:install_ffmpeg
echo [ffmpeg] Checking for FFmpeg...

if exist "%BIN_DIR%\ffmpeg.exe" (
    echo [ffmpeg] Found existing: %BIN_DIR%\ffmpeg.exe
    exit /b 0
)

REM Check if ffmpeg exists in system PATH
for /f "delims=" %%I in ('where ffmpeg.exe 2^>nul') do (
    echo [ffmpeg] Found system ffmpeg: %%I
    copy /y "%%I" "%BIN_DIR%\ffmpeg.exe" >nul 2>&1
    if exist "%BIN_DIR%\ffmpeg.exe" (
        echo [ffmpeg] Copied to %BIN_DIR%\ffmpeg.exe
        exit /b 0
    )
)

echo [ffmpeg] Downloading FFmpeg (gyan.dev essentials build)...

set "FFMPEG_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
set "FFMPEG_ZIP=%DOWNLOADS_DIR%\ffmpeg.zip"
set "FFMPEG_EXTRACT=%DOWNLOADS_DIR%\ffmpeg_extracted"

call :download_file "%FFMPEG_URL%" "%FFMPEG_ZIP%"
if errorlevel 1 (
    echo [ffmpeg] Gyan.dev download failed, trying GitHub...
    set "FFMPEG_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    call :download_file "!FFMPEG_URL!" "%FFMPEG_ZIP%"
    if errorlevel 1 (
        echo [ffmpeg] ERROR: Failed to download FFmpeg.
        echo [ffmpeg] Please download from https://ffmpeg.org/download.html
        echo [ffmpeg] and place ffmpeg.exe in %BIN_DIR%
        exit /b 1
    )
)

echo [ffmpeg] Extracting archive...
if exist "%FFMPEG_EXTRACT%" rmdir /s /q "%FFMPEG_EXTRACT%"
mkdir "%FFMPEG_EXTRACT%"

call :expand_zip "%FFMPEG_ZIP%" "%FFMPEG_EXTRACT%"
if errorlevel 1 (
    echo [ffmpeg] ERROR: Failed to extract archive.
    exit /b 1
)

REM Find and copy ffmpeg.exe
for /r "%FFMPEG_EXTRACT%" %%F in (ffmpeg.exe) do (
    copy /y "%%F" "%BIN_DIR%\ffmpeg.exe" >nul 2>&1
    if exist "%BIN_DIR%\ffmpeg.exe" (
        echo [ffmpeg] Installed: %BIN_DIR%\ffmpeg.exe
        exit /b 0
    )
)

echo [ffmpeg] ERROR: ffmpeg.exe not found in archive.
exit /b 1

:: ----------------------------
:: Opus DLL Installation (MSYS2 Method)
:: ----------------------------
:install_opus
echo [opus] Checking for libopus-0.dll...

if exist "%BIN_DIR%\libopus-0.dll" (
    echo [opus] Found existing: %BIN_DIR%\libopus-0.dll
    exit /b 0
)

REM Check if opus exists in system PATH
for %%L in (libopus-0.dll libopus.dll opus.dll) do (
    for /f "delims=" %%I in ('where %%L 2^>nul') do (
        copy /y "%%I" "%BIN_DIR%\libopus-0.dll" >nul 2>&1
        if exist "%BIN_DIR%\libopus-0.dll" (
            echo [opus] Copied from system: %%I
            exit /b 0
        )
    )
)

echo [opus] Downloading libopus-0.dll from MSYS2 mirror...

REM First, ensure we have zstd to decompress .zst files
call :ensure_zstd
if errorlevel 1 (
    echo [opus] ERROR: Cannot obtain zstd decompressor.
    goto :opus_manual_instructions
)

REM Download MSYS2 opus package
set "OPUS_MSYS_URL=https://mirror.msys2.org/mingw/mingw64/mingw-w64-x86_64-opus-1.5.2-1-any.pkg.tar.zst"
set "OPUS_ZST=%DOWNLOADS_DIR%\opus.pkg.tar.zst"
set "OPUS_TAR=%DOWNLOADS_DIR%\opus.pkg.tar"
set "OPUS_EXTRACT=%DOWNLOADS_DIR%\opus_msys"

echo [opus] Downloading MSYS2 opus package...
call :download_file "%OPUS_MSYS_URL%" "%OPUS_ZST%"
if errorlevel 1 (
    REM Try alternative version
    echo [opus] Trying alternative package version...
    set "OPUS_MSYS_URL=https://mirror.msys2.org/mingw/mingw64/mingw-w64-x86_64-opus-1.6-1-any.pkg.tar.zst"
    call :download_file "!OPUS_MSYS_URL!" "%OPUS_ZST%"
    if errorlevel 1 (
        echo [opus] ERROR: Failed to download MSYS2 package.
        goto :opus_manual_instructions
    )
)

REM Decompress .zst to .tar using zstd
echo [opus] Decompressing .zst archive...
if exist "%OPUS_TAR%" del /q "%OPUS_TAR%" >nul 2>&1
"%BIN_DIR%\zstd.exe" -d "%OPUS_ZST%" -o "%OPUS_TAR%" >nul 2>&1
if errorlevel 1 (
    echo [opus] ERROR: Failed to decompress .zst file.
    goto :opus_manual_instructions
)

if not exist "%OPUS_TAR%" (
    echo [opus] ERROR: Decompression produced no output.
    goto :opus_manual_instructions
)

REM Extract .tar using Windows built-in tar command
echo [opus] Extracting .tar archive...
if exist "%OPUS_EXTRACT%" rmdir /s /q "%OPUS_EXTRACT%"
mkdir "%OPUS_EXTRACT%"

tar -xf "%OPUS_TAR%" -C "%OPUS_EXTRACT%" >nul 2>&1
if errorlevel 1 (
    echo [opus] ERROR: Failed to extract .tar file.
    goto :opus_manual_instructions
)

REM Find and copy libopus-0.dll
echo [opus] Locating libopus-0.dll...
for /r "%OPUS_EXTRACT%" %%F in (libopus-0.dll) do (
    echo [opus] Found: %%F
    copy /y "%%F" "%BIN_DIR%\libopus-0.dll" >nul 2>&1
    if exist "%BIN_DIR%\libopus-0.dll" (
        echo [opus] Installed: %BIN_DIR%\libopus-0.dll
        exit /b 0
    )
)

echo [opus] ERROR: libopus-0.dll not found in package.
goto :opus_manual_instructions

:opus_manual_instructions
echo.
echo [opus] WARNING: Could not automatically install libopus-0.dll
echo [opus] Voice playback may not work without it.
echo.
echo [opus] Manual installation options:
echo   1. Install MSYS2 and run: pacman -S mingw-w64-x86_64-opus
echo   2. Download from https://opus-codec.org/downloads/
echo   3. Place libopus-0.dll in %BIN_DIR%
echo.
echo [opus] Continuing setup without opus...
exit /b 0

:: ----------------------------
:: Ensure zstd.exe is available
:: ----------------------------
:ensure_zstd
if exist "%BIN_DIR%\zstd.exe" (
    echo [zstd] Found existing: %BIN_DIR%\zstd.exe
    exit /b 0
)

echo [zstd] Downloading zstd decompressor...

REM Download portable zstd from GitHub releases
set "ZSTD_URL=https://github.com/facebook/zstd/releases/download/v1.5.6/zstd-v1.5.6-win64.zip"
set "ZSTD_ZIP=%DOWNLOADS_DIR%\zstd.zip"
set "ZSTD_EXTRACT=%DOWNLOADS_DIR%\zstd_extracted"

call :download_file "%ZSTD_URL%" "%ZSTD_ZIP%"
if errorlevel 1 (
    echo [zstd] ERROR: Failed to download zstd.
    exit /b 1
)

echo [zstd] Extracting...
if exist "%ZSTD_EXTRACT%" rmdir /s /q "%ZSTD_EXTRACT%"
mkdir "%ZSTD_EXTRACT%"

call :expand_zip "%ZSTD_ZIP%" "%ZSTD_EXTRACT%"
if errorlevel 1 (
    echo [zstd] ERROR: Failed to extract zstd archive.
    exit /b 1
)

REM Find and copy zstd.exe
for /r "%ZSTD_EXTRACT%" %%F in (zstd.exe) do (
    copy /y "%%F" "%BIN_DIR%\zstd.exe" >nul 2>&1
    if exist "%BIN_DIR%\zstd.exe" (
        echo [zstd] Installed: %BIN_DIR%\zstd.exe
        exit /b 0
    )
)

echo [zstd] ERROR: zstd.exe not found in archive.
exit /b 1

:: ----------------------------
:: Python Virtual Environment
:: ----------------------------
:ensure_virtualenv
echo [python] Checking for Python...

if exist ".venv\Scripts\python.exe" (
    echo [python] Found existing virtual environment.
    exit /b 0
)

REM Find Python
set "PYEXE="

REM Try py launcher (most reliable on Windows)
where py >nul 2>&1
if not errorlevel 1 (
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        set "PYEXE=py -3"
        goto :create_venv
    )
    py --version >nul 2>&1
    if not errorlevel 1 (
        set "PYEXE=py"
        goto :create_venv
    )
)

REM Try python3.exe or python.exe
for %%P in (python3.exe python.exe) do (
    where %%P >nul 2>&1
    if not errorlevel 1 (
        set "PYEXE=%%P"
        goto :create_venv
    )
)

REM Check default installation paths
for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYEXE=%%D\python.exe"
        goto :create_venv
    )
)

if not defined PYEXE (
    echo [python] ERROR: Python 3 not found!
    echo [python] Please install Python 3.10+ from https://python.org
    echo [python] Make sure to check "Add Python to PATH" during installation.
    exit /b 1
)

:create_venv
echo [python] Found Python, creating virtual environment...
echo [python] Using: %PYEXE%

%PYEXE% -m venv ".venv"
if errorlevel 1 (
    echo [python] ERROR: Failed to create virtual environment.
    echo [python] Possible solutions:
    echo   1. Reinstall Python
    echo   2. Run: python -m ensurepip
    echo   3. Ensure venv module is installed
    exit /b 1
)

echo [python] Virtual environment created: .venv
exit /b 0

:: ----------------------------
:: Python Dependencies
:: ----------------------------
:install_python_deps
echo [python] Installing dependencies...

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [python] ERROR: Venv python not found: %VENV_PY%
    exit /b 1
)

echo [python] Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip >nul 2>&1

if exist "requirements.txt" (
    echo [python] Installing from requirements.txt...
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [python] ERROR: Failed to install dependencies.
        exit /b 1
    )
) else if exist "pyproject.toml" (
    echo [python] Installing from pyproject.toml...
    "%VENV_PY%" -m pip install -e .
    if errorlevel 1 (
        echo [python] ERROR: Failed to install package.
        exit /b 1
    )
) else (
    echo [python] ERROR: No requirements.txt or pyproject.toml found.
    exit /b 1
)

echo [python] Testing module import...
"%VENV_PY%" -c "import dje; print('[python] dje module loaded successfully')" 2>nul
if errorlevel 1 (
    echo [python] WARNING: dje module import failed, but dependencies may still work.
)

exit /b 0

:: ----------------------------
:: Summary
:: ----------------------------
:show_summary
echo.
echo ========================================
echo       Setup Completed Successfully!
echo ========================================
echo.
if exist "%BIN_DIR%\ffmpeg.exe" (
    echo [OK] FFmpeg: %BIN_DIR%\ffmpeg.exe
) else (
    echo [?]  FFmpeg: Will use system PATH
)

if exist "%BIN_DIR%\libopus-0.dll" (
    echo [OK] Opus: %BIN_DIR%\libopus-0.dll
) else (
    echo [!]  Opus: Not found - voice may not work
)

echo [OK] Python venv: %CD%\.venv
echo.
echo To run the bot: run.bat
echo.
goto :eof

:: ----------------------------
:: Helper Functions
:: ----------------------------
:download_file
:: Usage: call :download_file "URL" "DESTINATION"
set "DL_URL=%~1"
set "DL_DEST=%~2"

echo [download] %DL_URL%

REM Try curl first (default on Windows 10+)
where curl.exe >nul 2>&1
if not errorlevel 1 (
    curl.exe -L --retry 3 --retry-delay 2 --connect-timeout 30 -o "%DL_DEST%" "%DL_URL%" 2>nul
    if exist "%DL_DEST%" (
        for %%A in ("%DL_DEST%") do (
            if %%~zA GTR 0 (
                echo [download] Success (curl)
                exit /b 0
            )
        )
    )
)

REM Try PowerShell
echo [download] curl failed, trying PowerShell...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { (New-Object Net.WebClient).DownloadFile('%DL_URL%', '%DL_DEST%'); exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"

if exist "%DL_DEST%" (
    for %%A in ("%DL_DEST%") do (
        if %%~zA GTR 0 (
            echo [download] Success (PowerShell)
            exit /b 0
        )
    )
)

echo [download] ERROR: Failed to download file
exit /b 1

:expand_zip
:: Usage: call :expand_zip "ZIP_FILE" "DESTINATION_FOLDER"
set "ZIP_FILE=%~1"
set "ZIP_DEST=%~2"

echo [archive] Extracting: %ZIP_FILE%

REM Use PowerShell Expand-Archive
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { Expand-Archive -LiteralPath '%ZIP_FILE%' -DestinationPath '%ZIP_DEST%' -Force -ErrorAction Stop; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo [archive] ERROR: Failed to extract archive
    exit /b 1
)

echo [archive] Success
exit /b 0

:setup_failed
echo.
echo ========================================
echo          Setup Failed!
echo ========================================
echo.
echo Please check the errors above and try again.
echo For help: https://github.com/gkhntpbs/Dje
echo.
exit /b 1
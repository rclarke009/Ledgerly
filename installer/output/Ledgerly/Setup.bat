@echo off
setlocal EnableDelayedExpansion
set "FAIL=0"
set "INSTALL_DIR=%LocalAppData%\Ledgerly"
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

echo.
echo ========================================
echo   Ledgerly Setup
echo ========================================
echo.
echo Source folder:  %HERE%
echo Install folder: %INSTALL_DIR%
echo.

:: --- Step 1: required files in source folder ---
echo [Step 1/5] Checking this folder has the Ledgerly files...
set "STEP1_OK=1"
if not exist "%HERE%\Setup.bat" set "STEP1_OK=0"
if not exist "%HERE%\Start.bat" set "STEP1_OK=0"
if not exist "%HERE%\docker-compose.yml" set "STEP1_OK=0"
if "!STEP1_OK!"=="0" (
  echo   [FAILED] Missing Setup.bat, Start.bat, or docker-compose.yml here.
  echo   Make sure you extracted the full ZIP and run Setup.bat from inside the Ledgerly folder.
  set /a FAIL+=1
  goto :summary
)
echo   [OK] Found Setup.bat, Start.bat, and docker-compose.yml.

:: --- Step 2: create install folder ---
echo.
echo [Step 2/5] Creating install folder...
if not exist "%INSTALL_DIR%" (
  mkdir "%INSTALL_DIR%" 2>nul
)
if not exist "%INSTALL_DIR%" (
  echo   [FAILED] Could not create: %INSTALL_DIR%
  set /a FAIL+=1
  goto :summary
)
echo   [OK] Install folder exists: %INSTALL_DIR%

:: --- Step 3: copy files ---
echo.
echo [Step 3/5] Copying files to install folder (may take a minute)...
robocopy "%HERE%" "%INSTALL_DIR%" /E /XD .git __pycache__ .venv installer .idea .vscode /XF .env *.zip /NFL /NDL /NJH /NJS /nc /ns /np
set "ROBOCODE=!ERRORLEVEL!"
if !ROBOCODE! GEQ 8 (
  echo   [FAILED] Copy failed (robocopy exit code !ROBOCODE!).
  set /a FAIL+=1
  goto :summary
)
if not exist "%INSTALL_DIR%\Start.bat" (
  echo   [FAILED] Copy finished but Start.bat is missing in the install folder.
  set /a FAIL+=1
  goto :summary
)
if not exist "%INSTALL_DIR%\docker-compose.yml" (
  echo   [FAILED] Copy finished but docker-compose.yml is missing in the install folder.
  set /a FAIL+=1
  goto :summary
)
echo   [OK] Files copied to %INSTALL_DIR%

:: --- Step 4: .env ---
echo.
echo [Step 4/5] Setting up .env configuration...
if exist "%INSTALL_DIR%\.env" (
  echo   [OK] .env already exists — left unchanged.
) else if exist "%INSTALL_DIR%\.env.portable-xps15.example" (
  copy /Y "%INSTALL_DIR%\.env.portable-xps15.example" "%INSTALL_DIR%\.env" >nul
  if exist "%INSTALL_DIR%\.env" (
    echo   [OK] Created .env from portable XPS 15 profile (cool/quiet defaults).
  ) else (
    echo   [FAILED] Could not create .env from .env.portable-xps15.example
    set /a FAIL+=1
  )
) else if exist "%INSTALL_DIR%\.env.example" (
  copy /Y "%INSTALL_DIR%\.env.example" "%INSTALL_DIR%\.env" >nul
  if exist "%INSTALL_DIR%\.env" (
    echo   [OK] Created .env from .env.example.
  ) else (
    echo   [FAILED] Could not create .env from .env.example
    set /a FAIL+=1
  )
) else (
  echo   [WARNING] No .env template found — you may need to create .env manually.
)

:: --- Step 5: desktop shortcut ---
echo.
echo [Step 5/5] Creating desktop shortcut...
set "SHORTCUT_OK=0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $desk = [Environment]::GetFolderPath('Desktop'); $lnk = Join-Path $desk 'Ledgerly.lnk'; $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk); $s.TargetPath = '%INSTALL_DIR%\Start.bat'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'Start Ledgerly (Docker)'; $s.Save(); if (-not (Test-Path -LiteralPath $lnk)) { exit 1 }; Write-Host ('   Desktop shortcut: ' + $lnk); exit 0 } catch { Write-Host ('   ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 (
  echo   [FAILED] Could not create desktop shortcut.
  echo   You can still start Ledgerly by double-clicking:
  echo     %INSTALL_DIR%\Start.bat
  set /a FAIL+=1
) else (
  set "SHORTCUT_OK=1"
  echo   [OK] Desktop shortcut created (Ledgerly.lnk).
)

:summary
echo.
echo ========================================
if "!FAIL!"=="0" (
  echo   INSTALLATION SUCCEEDED
  echo ========================================
  echo.
  echo Installed to: %INSTALL_DIR%
  if "!SHORTCUT_OK!"=="1" (
    echo Next step:     Start Docker Desktop, then double-click the Ledgerly shortcut on your desktop.
  ) else (
    echo Next step:     Start Docker Desktop, then double-click:
    echo                %INSTALL_DIR%\Start.bat
  )
  echo Browser URL:   http://localhost:8000/
  echo.
  echo You can delete the folder you extracted from the ZIP if you like.
) else (
  echo   INSTALLATION FAILED — !FAIL! problem(s^) above
  echo ========================================
  echo.
  echo Do not close this window yet. Read the [FAILED] lines above.
  echo.
  echo Common fixes:
  echo   - Extract the full ZIP to Downloads, then run Setup.bat from inside the Ledgerly folder.
  echo   - Do not run Setup from inside the ZIP file without extracting.
  echo   - If copy failed, check disk space and try again.
)
echo.
pause
if not "!FAIL!"=="0" exit /b 1
exit /b 0

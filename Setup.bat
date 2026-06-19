@echo off
setlocal
set "INSTALL_DIR=%LocalAppData%\Ledgerly"
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

echo Installing Ledgerly to %INSTALL_DIR%...
mkdir "%INSTALL_DIR%" 2>nul

:: Copy files, excluding dev/secrets and installer build artifacts
robocopy "%HERE%" "%INSTALL_DIR%" /E /XD .git __pycache__ .venv installer .idea .vscode /XF .env *.zip /NFL /NDL /NJH /NJS /nc /ns /np
if errorlevel 8 (
  echo Robocopy failed.
  pause
  exit /b 1
)

:: First-time .env: prefer Dad's XPS 15 portable template, else generic example
if not exist "%INSTALL_DIR%\.env" (
  if exist "%INSTALL_DIR%\.env.portable-xps15.example" (
    copy /Y "%INSTALL_DIR%\.env.portable-xps15.example" "%INSTALL_DIR%\.env" >nul
    echo Created .env from portable XPS 15 profile (cool/quiet defaults).
  ) else if exist "%INSTALL_DIR%\.env.example" (
    copy /Y "%INSTALL_DIR%\.env.example" "%INSTALL_DIR%\.env" >nul
    echo Created .env from .env.example.
  )
)

:: Create desktop shortcut (PowerShell)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$WshShell = New-Object -ComObject WScript.Shell;" ^
  "$Shortcut = $WshShell.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\\Ledgerly.lnk');" ^
  "$Shortcut.TargetPath = '%INSTALL_DIR%\Start.bat';" ^
  "$Shortcut.WorkingDirectory = '%INSTALL_DIR%';" ^
  "$Shortcut.Description = 'Start Ledgerly (Docker)';" ^
  "$Shortcut.Save()"

echo.
echo Installation complete. A "Ledgerly" shortcut is on your desktop.
echo You can close this window and delete the folder you extracted if you like.
echo.
echo To start: double-click the desktop shortcut (Docker must be running).
pause

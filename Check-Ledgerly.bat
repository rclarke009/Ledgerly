@echo off
setlocal EnableDelayedExpansion
set "FAIL=0"
set "WARN=0"
set "INSTALL=%LocalAppData%\Ledgerly"
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "LOG=%USERPROFILE%\Desktop\ledgerly-diagnose.txt"

echo.
echo ========================================
echo   Ledgerly Check
echo ========================================
echo.
echo This script checks install locations, Docker, and whether the app is running.
echo A full report is saved to your Desktop: ledgerly-diagnose.txt
echo.

> "%LOG%" echo Ledgerly diagnose — %DATE% %TIME%
>>"%LOG%" echo Computer: %COMPUTERNAME%  User: %USERNAME%
>>"%LOG%" echo Launched from: %HERE%
>>"%LOG%" echo Install folder: %INSTALL%
>>"%LOG%" echo.

call :section "1. Install folder (%LocalAppData%\Ledgerly)"
if not exist "%INSTALL%" (
  call :fail "Install folder does not exist: %INSTALL%"
  call :hint "Run Setup.bat once from the extracted Ledgerly folder."
  goto :docker_skip
)
call :ok "Install folder exists"

if not exist "%INSTALL%\Start.bat" call :fail "Missing %INSTALL%\Start.bat"
if not exist "%INSTALL%\Setup.bat" call :fail "Missing %INSTALL%\Setup.bat"
if not exist "%INSTALL%\Check-Ledgerly.bat" call :warn "Missing %INSTALL%\Check-Ledgerly.bat (re-run Setup.bat to update install)"
if not exist "%INSTALL%\docker-compose.yml" call :fail "Missing %INSTALL%\docker-compose.yml"
if not exist "%INSTALL%\.env" (
  call :warn "No .env in install folder — run Setup.bat or copy .env.portable-xps15.example to .env"
) else (
  call :ok ".env present"
)

if /I not "%HERE%"=="%INSTALL%" (
  if exist "%HERE%\docker-compose.yml" (
    call :warn "You ran Check from the extract/source folder, not the install folder."
    call :hint "Installed copy is at %INSTALL%. Start Ledgerly with Start.bat there."
  )
) else (
  call :ok "Running from install folder"
)

call :section "2. Desktop shortcut"
set "DESKTOP=%USERPROFILE%\Desktop"
if exist "%DESKTOP%\Ledgerly.lnk" (
  call :ok "Desktop shortcut exists: %DESKTOP%\Ledgerly.lnk"
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { $s = (New-Object -ComObject WScript.Shell).CreateShortcut('%DESKTOP%\Ledgerly.lnk'); Write-Output ('Target: ' + $s.TargetPath); Write-Output ('Working dir: ' + $s.WorkingDirectory) } catch { Write-Output ('Could not read shortcut: ' + $_.Exception.Message) }" >>"%LOG%" 2>&1
) else (
  call :warn "No Ledgerly.lnk on Desktop — use Win+R, paste %%LocalAppData%%\Ledgerly, double-click Start.bat"
)

:docker_skip
call :section "3. Docker"
where docker >nul 2>&1
if errorlevel 1 (
  call :fail "Docker command not found — install Docker Desktop from docker.com"
  goto :finish
)
call :ok "docker command found on PATH"
>>"%LOG%" echo. >>"%LOG%" echo --- docker info --- >>"%LOG%"
docker info >>"%LOG%" 2>&1
if errorlevel 1 (
  call :fail "Docker Desktop is not running — start Docker Desktop and wait for the whale icon"
  goto :finish
)
call :ok "Docker Desktop is running"

if not exist "%INSTALL%\docker-compose.yml" goto :finish

pushd "%INSTALL%"
call :section "4. Docker containers (docker compose ps)"
>>"%LOG%" echo. >>"%LOG%" echo --- docker compose ps --- >>"%LOG%"
docker compose ps >>"%LOG%" 2>&1
docker compose ps 2>nul | findstr /I "ledgerly-app" >nul 2>&1
if errorlevel 1 (
  call :warn "ledgerly-app container is not running — double-click Start.bat and leave the window open"
) else (
  docker compose ps 2>nul | findstr /I "Up" | findstr /I "ledgerly-app" >nul 2>&1
  if errorlevel 1 (
    call :warn "ledgerly-app exists but may not be Up — see docker compose ps in the log file"
  ) else (
    call :ok "ledgerly-app container is Up"
  )
)

call :section "5. Port 8000 and web health"
netstat -ano 2>nul | findstr /R /C:":8000 " >>"%LOG%" 2>&1
netstat -ano 2>nul | findstr /R /C:":8000 " >nul 2>&1
if errorlevel 1 (
  call :warn "Nothing listening on port 8000 — Start.bat may not have finished, or the app failed to start"
) else (
  call :ok "Something is using port 8000 (see log for netstat lines)"
)

set "HEALTH_OK=0"
where curl >nul 2>&1
if not errorlevel 1 (
  >>"%LOG%" echo. >>"%LOG%" echo --- curl http://localhost:8000/health ---
  curl -sf http://localhost:8000/health >>"%LOG%" 2>&1
  curl -sf http://localhost:8000/health 2>nul | findstr /C:"\"healthy\":true" >nul 2>&1
  if not errorlevel 1 set "HEALTH_OK=1"
)
if "!HEALTH_OK!"=="0" (
  powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8000/health' -UseBasicParsing -TimeoutSec 5; $r.Content | Out-File -FilePath '%LOG%' -Append -Encoding utf8; if ($r.Content -match '\"healthy\"\s*:\s*true') { exit 0 } else { exit 1 } } catch { 'Health check failed: ' + $_.Exception.Message | Out-File -FilePath '%LOG%' -Append -Encoding utf8; exit 1 }" >nul 2>&1
  if not errorlevel 1 set "HEALTH_OK=1"
)
if "!HEALTH_OK!"=="1" (
  call :ok "Web app health check passed — open http://localhost:8000/"
) else (
  call :fail "Web app not healthy at http://localhost:8000/health"
  call :hint "Run Start.bat, leave the window open 1-3 min (first run can take 15-45+ min for downloads)."
)

call :section "6. Recent container logs (last 25 lines each)"
for %%S in (ledgerly postgres ollama) do (
  >>"%LOG%" echo. >>"%LOG%" echo --- docker compose logs --tail 25 %%S ---
  docker compose logs --tail 25 %%S >>"%LOG%" 2>&1
)
popd

:finish
call :section "Summary"
>>"%LOG%" echo. >>"%LOG%" echo ======================================== >>"%LOG%"
if "!FAIL!"=="0" (
  if "!WARN!"=="0" (
    >>"%LOG%" echo RESULT: All checks passed.
    echo   [OK] All checks passed.
    echo.
    echo Ledgerly looks ready. Open http://localhost:8000/ in your browser.
  ) else (
    >>"%LOG%" echo RESULT: No hard failures, but !WARN! warning(s^) — read [WARNING] lines above.
    echo   [WARNING] !WARN! warning(s^) — see details above and in the log file.
    echo.
    echo Try Start.bat from %%LocalAppData%%\Ledgerly if the app is not open yet.
  )
) else (
  >>"%LOG%" echo RESULT: !FAIL! problem(s^) found — read [FAILED] lines above.
  echo   [FAILED] !FAIL! problem(s^) — read the lines above before closing this window.
)
>>"%LOG%" echo Full log: %LOG%
echo.
echo Report saved to: %LOG%
echo.

if not "!FAIL!"=="0" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Ledgerly found !FAIL! problem(s). Read the black window and send Desktop\ledgerly-diagnose.txt to support.','Ledgerly Check','OK','Warning')" 2>nul
) else if not "!WARN!"=="0" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Checks passed with warnings. See Desktop\ledgerly-diagnose.txt for details.','Ledgerly Check','OK','Information')" 2>nul
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('All checks passed. Open http://localhost:8000/ in your browser.','Ledgerly Check','OK','Information')" 2>nul
)

echo Press any key to close...
pause >nul
if not "!FAIL!"=="0" exit /b 1
exit /b 0

:section
echo.
echo %~1
>>"%LOG%" echo %~1
goto :eof

:ok
echo   [OK] %~1
echo   [OK] %~1 >>"%LOG%"
goto :eof

:warn
echo   [WARNING] %~1
echo   [WARNING] %~1 >>"%LOG%"
set /a WARN+=1
goto :eof

:fail
echo   [FAILED] %~1
echo   [FAILED] %~1 >>"%LOG%"
set /a FAIL+=1
goto :eof

:hint
echo          ^> %~1
echo          ^> %~1 >>"%LOG%"
goto :eof

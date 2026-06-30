@echo off
setlocal EnableDelayedExpansion
set "FAIL=0"
cd /d "%~dp0"

echo.
echo ========================================
echo   Ledgerly Start
echo ========================================
echo.
echo Working folder: %CD%
echo Browser URL:    http://localhost:8000/
echo.

:: --- Step 1: prerequisites ---
echo [Step 1/7] Checking prerequisites...
if not exist "docker-compose.yml" (
  echo   [FAILED] docker-compose.yml not found in %CD%
  echo   Run Setup.bat first, or double-click Start.bat from the Ledgerly install folder.
  set /a FAIL+=1
  goto :summary
)
echo   [OK] Found docker-compose.yml

where docker >nul 2>&1
if errorlevel 1 (
  echo   [FAILED] Docker command not found. Install Docker Desktop from docker.com
  set /a FAIL+=1
  goto :summary
)
docker info >nul 2>&1
if errorlevel 1 (
  echo   [FAILED] Docker Desktop is not running. Start Docker Desktop, wait for the whale icon, then try again.
  set /a FAIL+=1
  goto :summary
)
echo   [OK] Docker is running

if not defined OLLAMA_NUM_THREADS (
  findstr /R /C:"^OLLAMA_NUM_THREADS=" .env >nul 2>&1
  if errorlevel 1 (
    for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$c=(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors; if($c -le 2){1}else{[Math]::Max(1,[Math]::Min([Math]::Min([math]::Floor($c/2),$c-1),8))}"`) do (
      set "OLLAMA_NUM_THREADS=%%i"
    )
    echo   [OK] OLLAMA_NUM_THREADS=!OLLAMA_NUM_THREADS! (auto-detected, conservative)
  )
)

:: --- Open startup page (polls /health until ready) ---
if exist "%CD%\starting.html" (
  echo.
  echo Opening startup page in your browser...
  start "" "%CD%\starting.html"
  echo   [OK] starting.html opened — it will redirect when Ledgerly is ready.
) else (
  echo   [WARNING] starting.html not found — watch this window for progress.
)

:: --- Step 2: pull container images (visible progress) ---
echo.
echo [Step 2/7] Downloading Docker images (first run may take several minutes)...
docker compose pull
if errorlevel 1 (
  echo   [FAILED] docker compose pull failed.
  echo   Check your internet connection and Docker Desktop, then try again.
  set /a FAIL+=1
  goto :summary
)
echo   [OK] Docker images ready.

:: --- Step 3: start containers ---
echo.
echo [Step 3/7] Starting Docker containers...
docker compose up -d
if errorlevel 1 (
  echo   [FAILED] docker compose up failed.
  echo   Check Docker Desktop is running and no other app is blocking port 8000.
  set /a FAIL+=1
  goto :summary
)
echo   [OK] Containers started.
echo   Finance MCP (optional): http://localhost:8001/mcp

:: --- Step 4: wait for Ollama ---
echo.
echo [Step 4/7] Waiting for Ollama to be ready...
set "WAIT_COUNT=0"
set "WAIT_SEC=3"
:wait_ollama
docker compose exec ollama ollama list >nul 2>&1
if errorlevel 1 (
  set /a WAIT_COUNT+=1
  if !WAIT_COUNT! EQU 1 echo   ... starting Ollama (this is normal on first run^)
  set /a MOD=WAIT_COUNT %% 10
  if !MOD! EQU 0 (
    set /a ELAPSED_SEC=WAIT_COUNT*WAIT_SEC
    set /a ELAPSED_MIN=ELAPSED_SEC/60
    echo   ... still waiting for Ollama (~!ELAPSED_MIN! min elapsed^)
  )
  timeout /t !WAIT_SEC! /nobreak >nul
  goto wait_ollama
)
echo   [OK] Ollama is ready.

:: --- Step 5: models ---
echo.
echo [Step 5/7] Checking AI models (first download can take 15-45+ minutes)...
set "PORTABLE="
findstr /R /C:"^LEDGERLY_PROFILE=portable" /C:"^LEDGERLY_PROFILE=low_spec" /C:"^FINELLY_PROFILE=portable" /C:"^FINELLY_PROFILE=low_spec" .env >nul 2>&1
if not errorlevel 1 set "PORTABLE=1"

set "MODEL_TOTAL=3"
set "MODEL_IDX=0"
if defined PORTABLE (
  set /a MODEL_IDX+=1
  call :ensure_model "qwen2.5:3b" !MODEL_IDX! !MODEL_TOTAL!
  set /a MODEL_IDX+=1
  call :ensure_model "moondream" !MODEL_IDX! !MODEL_TOTAL!
) else (
  set /a MODEL_IDX+=1
  call :ensure_model "qwen3:8b" !MODEL_IDX! !MODEL_TOTAL!
  set /a MODEL_IDX+=1
  call :ensure_model "llava:7b" !MODEL_IDX! !MODEL_TOTAL!
)
set /a MODEL_IDX+=1
call :ensure_model "nomic-embed-text" !MODEL_IDX! !MODEL_TOTAL!

:: --- Step 6: wait for web app ---
echo.
echo [Step 6/7] Waiting for Ledgerly web app at http://localhost:8000/health ...
set "APP_WAIT=0"
set "APP_WAIT_SEC=2"
:wait_app
set "HEALTH_OK=0"
where curl >nul 2>&1
if not errorlevel 1 (
  curl -sf http://localhost:8000/health 2>nul | findstr /C:"\"healthy\":true" >nul 2>&1
  if not errorlevel 1 set "HEALTH_OK=1"
) else (
  powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8000/health' -UseBasicParsing -TimeoutSec 5; if ($r.Content -match '\"healthy\"\s*:\s*true') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 set "HEALTH_OK=1"
)
if "!HEALTH_OK!"=="1" goto :app_ready
set /a APP_WAIT+=1
if !APP_WAIT! EQU 1 echo   ... starting web app (this is normal^)
set /a MOD=APP_WAIT %% 15
if !MOD! EQU 0 (
  set /a ELAPSED_SEC=APP_WAIT*APP_WAIT_SEC
  set /a ELAPSED_MIN=ELAPSED_SEC/60
  echo   ... still waiting for web app (~!ELAPSED_MIN! min elapsed^) — starting.html will open the app when ready
)
timeout /t !APP_WAIT_SEC! /nobreak >nul
goto wait_app

:app_ready
echo   [OK] Web app is healthy.

:: --- Step 7: done (starting.html handles browser redirect) ---
echo.
echo [Step 7/7] Startup complete.
echo   [OK] If your browser is on the Starting Ledgerly page, it should redirect now.
echo   [OK] Otherwise open: http://localhost:8000/
goto :summary

:ensure_model
set "MODEL_NAME=%~1"
set "MODEL_N=%~2"
set "MODEL_T=%~3"
docker compose exec ollama ollama list 2>nul | findstr /C:"!MODEL_NAME!" >nul 2>&1
if not errorlevel 1 (
  echo   [OK] Model !MODEL_N! of !MODEL_T!: !MODEL_NAME! already present.
  goto :eof
)
echo   ... Model !MODEL_N! of !MODEL_T!: pulling !MODEL_NAME! (download in progress — do not close this window^)
docker compose exec ollama ollama pull !MODEL_NAME!
if errorlevel 1 (
  echo   [FAILED] Could not pull !MODEL_NAME!
  set /a FAIL+=1
) else (
  echo   [OK] !MODEL_NAME! downloaded.
)
goto :eof

:summary
echo.
echo ========================================
if "!FAIL!"=="0" (
  echo   LEDGERLY IS READY
  echo ========================================
  echo.
  echo Open in your browser: http://localhost:8000/
  echo The startup page should redirect automatically if it is still open.
  echo To stop later:        docker compose down
  echo   (run that from this folder: %CD%^)
) else (
  echo   START FAILED — !FAIL! problem(s^) above
  echo ========================================
  echo.
  echo Read the [FAILED] lines above before closing this window.
  echo You can still try opening http://localhost:8000/ in your browser.
  echo.
  echo Common fixes:
  echo   - Start Docker Desktop and wait until it is fully running.
  echo   - Stop an old "finelly" stack in Docker Desktop if port 8000 is in use.
  echo   - Run Start.bat from %LocalAppData%\Ledgerly or the extracted Ledgerly folder.
)
echo.
pause
if not "!FAIL!"=="0" exit /b 1
exit /b 0

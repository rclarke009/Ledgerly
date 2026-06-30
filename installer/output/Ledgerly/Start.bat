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
echo [Step 1/6] Checking prerequisites...
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

:: --- Step 2: start containers ---
echo.
echo [Step 2/6] Starting Docker containers (first run may download images — can take several minutes)...
docker compose up -d
if errorlevel 1 (
  echo   [FAILED] docker compose up failed.
  echo   Check Docker Desktop is running and no other app is blocking port 8000.
  set /a FAIL+=1
  goto :summary
)
echo   [OK] Containers started.
echo   Finance MCP (optional): http://localhost:8001/mcp

:: --- Step 3: wait for Ollama ---
echo.
echo [Step 3/6] Waiting for Ollama to be ready...
set "WAIT_COUNT=0"
:wait
docker compose exec ollama ollama list >nul 2>&1
if errorlevel 1 (
  set /a WAIT_COUNT+=1
  if !WAIT_COUNT! EQU 1 echo   ... starting Ollama (this is normal on first run)
  set /a MOD=WAIT_COUNT %% 10
  if !MOD! EQU 0 echo   ... still waiting for Ollama (!WAIT_COUNT! checks^)
  timeout /t 3 /nobreak >nul
  goto wait
)
echo   [OK] Ollama is ready.

:: --- Step 4: models ---
echo.
echo [Step 4/6] Checking AI models (first download can take 15-45+ minutes)...
set "PORTABLE="
findstr /R /C:"^LEDGERLY_PROFILE=portable" /C:"^LEDGERLY_PROFILE=low_spec" /C:"^FINELLY_PROFILE=portable" /C:"^FINELLY_PROFILE=low_spec" .env >nul 2>&1
if not errorlevel 1 set "PORTABLE=1"

if defined PORTABLE (
  call :ensure_model "qwen2.5:3b"
  call :ensure_model "moondream"
) else (
  call :ensure_model "qwen3:8b"
  call :ensure_model "llava:7b"
)
call :ensure_model "nomic-embed-text"

:: --- Step 5: wait for web app ---
echo.
echo [Step 5/6] Waiting for Ledgerly web app at http://localhost:8000/health ...
where curl >nul 2>&1
if errorlevel 1 (
  echo   [WARNING] curl not found — cannot auto-check health. Open http://localhost:8000/ in your browser.
  goto :open_browser
)
set "APP_WAIT=0"
:waitapp
curl -sf http://localhost:8000/health 2>nul | findstr /C:"\"healthy\":true" >nul 2>&1
if errorlevel 1 (
  set /a APP_WAIT+=1
  if !APP_WAIT! EQU 1 echo   ... starting web app (this is normal)
  set /a MOD=APP_WAIT %% 15
  if !MOD! EQU 0 echo   ... still waiting for web app (!APP_WAIT! checks^) — open http://localhost:8000/ anytime
  timeout /t 2 /nobreak >nul
  goto waitapp
)
echo   [OK] Web app is healthy.

:: --- Step 6: open browser ---
:open_browser
echo.
echo [Step 6/6] Opening browser...
start http://localhost:8000/
echo   [OK] Opened http://localhost:8000/
goto :summary

:ensure_model
docker compose exec ollama ollama list 2>nul | findstr /C:"%~1" >nul 2>&1
if not errorlevel 1 (
  echo   [OK] %~1 already present.
  goto :eof
)
echo   ... pulling %~1 (download in progress — do not close this window^)
docker compose exec ollama ollama pull %~1
if errorlevel 1 (
  echo   [FAILED] Could not pull %~1
  set /a FAIL+=1
) else (
  echo   [OK] %~1 downloaded.
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

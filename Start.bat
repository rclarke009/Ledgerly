@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

if not defined OLLAMA_NUM_THREADS (
  findstr /R /C:"^OLLAMA_NUM_THREADS=" .env >nul 2>&1
  if errorlevel 1 (
    for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$c=(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors; if($c -le 2){1}else{[Math]::Max(1,[Math]::Min([Math]::Min([math]::Floor($c/2),$c-1),8))}"`) do (
      set "OLLAMA_NUM_THREADS=%%i"
    )
    echo OLLAMA_NUM_THREADS=!OLLAMA_NUM_THREADS! (auto-detected, conservative)
  )
)

echo Starting Ledgerly (Postgres+pgvector internal, Ollama, app, finance MCP)...
docker compose up -d
echo Finance tools MCP (optional, for Cursor): http://localhost:8001/mcp — set FINNHUB_API_KEY in .env for live quotes.

echo Waiting for Ollama to be ready...
:wait
docker compose exec ollama ollama list >nul 2>&1
if errorlevel 1 (
  timeout /t 3 /nobreak >nul
  goto wait
)

set "PORTABLE="
findstr /R /C:"^LEDGERLY_PROFILE=portable" /C:"^LEDGERLY_PROFILE=low_spec" /C:"^FINELLY_PROFILE=portable" /C:"^FINELLY_PROFILE=low_spec" .env >nul 2>&1
if not errorlevel 1 set "PORTABLE=1"

echo Checking models (skip if already installed)...
if defined PORTABLE (
  docker compose exec ollama ollama list 2>nul | findstr /C:"qwen2.5:3b" >nul 2>&1
  if errorlevel 1 (
    echo Pulling qwen2.5:3b...
    docker compose exec ollama ollama pull qwen2.5:3b
  ) else echo qwen2.5:3b already present.
  docker compose exec ollama ollama list 2>nul | findstr /C:"moondream" >nul 2>&1
  if errorlevel 1 (
    echo Pulling moondream...
    docker compose exec ollama ollama pull moondream
  ) else echo moondream already present.
) else (
  docker compose exec ollama ollama list 2>nul | findstr /C:"qwen3:8b" >nul 2>&1
  if errorlevel 1 (
    echo Pulling qwen3:8b...
    docker compose exec ollama ollama pull qwen3:8b
  ) else echo qwen3:8b already present.
  docker compose exec ollama ollama list 2>nul | findstr /C:"llava:7b" >nul 2>&1
  if errorlevel 1 (
    echo Pulling llava:7b...
    docker compose exec ollama ollama pull llava:7b
  ) else echo llava:7b already present.
)
docker compose exec ollama ollama list 2>nul | findstr /C:"nomic-embed-text" >nul 2>&1
if errorlevel 1 (
  echo Pulling nomic-embed-text...
  docker compose exec ollama ollama pull nomic-embed-text
) else echo nomic-embed-text already present.

echo Waiting for Ledgerly web app...
:waitapp
curl -sf http://localhost:8000/health 2>nul | findstr /C:"\"healthy\":true" >nul 2>&1
if errorlevel 1 (
  timeout /t 2 /nobreak >nul
  goto waitapp
)

echo.
echo Ready. Opening browser...
start http://localhost:8000/
echo To stop later: docker compose down
pause

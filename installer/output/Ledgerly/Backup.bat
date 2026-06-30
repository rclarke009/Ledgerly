@echo off
setlocal
cd /d "%~dp0"

if not exist "docker-compose.yml" (
  echo docker-compose.yml not found in this folder.
  pause
  exit /b 1
)

echo Backing up Ledgerly database...
echo Make sure Docker is running and Ledgerly has been started at least once (so the database exists).

docker compose exec -T postgres pg_isready -U ledgerly -d ledgerly >nul 2>&1
if errorlevel 1 (
  echo.
  echo Postgres is not ready. Start Ledgerly first (desktop shortcut), wait until Ready, then run this script again.
  pause
  exit /b 1
)

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "TS=%%i"
set "OUT=%USERPROFILE%\Desktop\ledgerly-backup-%TS%.dump"

docker compose exec -T postgres pg_dump -U ledgerly -d ledgerly -Fc -f /tmp/ledgerly-backup.dump
if errorlevel 1 (
  echo pg_dump failed.
  pause
  exit /b 1
)

docker compose cp postgres:/tmp/ledgerly-backup.dump "%OUT%"
if errorlevel 1 (
  echo Copy to host failed.
  pause
  exit /b 1
)

docker compose exec -T postgres rm -f /tmp/ledgerly-backup.dump

echo.
echo Backup saved: %OUT%
echo Keep this file somewhere safe (cloud drive, USB, etc.) before upgrades or moving PCs.
pause

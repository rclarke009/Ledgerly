@echo off
REM Build Ledgerly-Portable.zip using only Docker. No Inno Setup required.
REM Run from project root or from installer. Output: installer\output\Ledgerly-Portable.zip

cd /d "%~dp0"
set "SCRIPT_DIR=%~dp0"
set "REPO_ROOT=%SCRIPT_DIR%.."
set "OUT_DIR=%SCRIPT_DIR%output"
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

docker run --rm ^
  -v "%REPO_ROOT%:/src:ro" ^
  -v "%OUT_DIR%:/out" ^
  -w /work ^
  alpine:latest ^
  sh -c "apk add --no-cache zip >/dev/null && rm -rf /work && mkdir -p /work/Ledgerly && cd /src && for f in *; do case \"$f\" in .env|.git|__pycache__|.venv|installer|.idea|.vscode) ;; *) cp -R \"$f\" /work/Ledgerly/ 2>/dev/null ;; esac; done && for dot in .dockerignore .env.example .env.portable-xps15.example; do [ -f /src/$dot ] && cp /src/$dot /work/Ledgerly/; done && find /work/Ledgerly -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; find /work/Ledgerly -type d -name .venv -exec rm -rf {} + 2>/dev/null; find /work/Ledgerly -type f \( -name '*.sqlite' -o -name '*.db' -o -name '*.dump' \) -delete 2>/dev/null; find /work/Ledgerly -type f -name '.env' -delete 2>/dev/null; rm -f /work/Ledgerly/payload.json 2>/dev/null; (cd /work && zip -r /out/Ledgerly-Portable.zip Ledgerly -x \"*.DS_Store\" \"Ledgerly/installer/*\" \"*__pycache__*\" \"*.sqlite\" \"*.db\" \"*.dump\" \"Ledgerly/payload.json\" \"Ledgerly/.env\" \"*/*/.venv/*\")"

if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)
echo.
echo Built: %OUT_DIR%\Ledgerly-Portable.zip
echo Give that ZIP to your recipient. They unzip it, run Setup.bat once, then use the desktop shortcut.
pause

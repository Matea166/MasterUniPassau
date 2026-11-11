@echo off
rem One-button reproduction for Windows (works from CMD and PowerShell).
rem macOS/Linux: use ./reproduce_all.sh
rem
rem   reproduce_all.bat                          full Table 6.2 grid
rem   PowerShell: $env:QUICK=1; .\reproduce_all.bat    headline configs only
rem   PowerShell: $env:FRESH=0; .\reproduce_all.bat    keep the DB volume
rem
rem The experiment sequence itself runs inside the container
rem (scripts/run_all.sh); this wrapper only drives Docker, so the pipeline
rem is identical on every platform.

cd /d "%~dp0"

if "%QUICK%"=="" set QUICK=0
if "%FRESH%"=="" set FRESH=1

docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is not running - start Docker Desktop first.
    exit /b 1
)

if "%FRESH%"=="1" (
    echo === Removing previous containers and database volume ===
    docker compose down -v --remove-orphans
)

echo === Building self-contained images and starting services ===
docker compose up -d --build
if errorlevel 1 exit /b 1

docker compose exec -T -e QUICK=%QUICK% app bash scripts/run_all.sh
if errorlevel 1 exit /b 1

echo.
echo Done. All outputs are in .\results\.
echo Open .\results\index.html for the experiment report.

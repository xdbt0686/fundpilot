@echo off
title FundPilot Launcher

set "DIR=D:\LLM study\fundpilot"
set "PY=%DIR%\.venv\Scripts\python.exe"
set "MODEL=qwen2.5:3b"

cd /d "%DIR%"
if errorlevel 1 (
    echo ERROR: Cannot enter project directory: %DIR%
    pause
    exit /b 1
)

if not exist "%PY%" (
    echo ERROR: Python not found at %PY%
    pause
    exit /b 1
)

echo Project : %DIR%
echo Python  : %PY%
echo Model   : %MODEL%
echo.

powershell -NoProfile -Command "try{Invoke-WebRequest http://localhost:11434/ -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Ollama is not running.
    echo Please open another window and run:  ollama serve
    echo Then re-run this script.
    pause
    exit /b 1
)
echo Ollama  : running
echo.

echo Select mode:
echo   1  Dashboard + Monitor loop
echo   2  Agent chat  [3-layer AI]
echo   3  Buy recommendations  [NEW]
echo   4  Dashboard only
echo   5  Monitor loop only
echo   6  Overlap analysis
echo   7  Portfolio analysis
echo.
set /p "M=Enter number (1-7): "

if "%M%"=="1" goto FULL
if "%M%"=="2" goto AGENT
if "%M%"=="3" goto RECOMMEND
if "%M%"=="4" goto DASH
if "%M%"=="5" goto LOOP
if "%M%"=="6" goto OVERLAP
if "%M%"=="7" goto PORTFOLIO
echo Invalid choice.
pause
exit /b 1

:FULL
set OLLAMA_MODEL=%MODEL%
start "Monitor" cmd /k "cd /d "%DIR%" && set OLLAMA_MODEL=%MODEL% && "%PY%" run_monitor_loop.py"
start "Dashboard" cmd /k "cd /d "%DIR%" && set OLLAMA_MODEL=%MODEL% && "%PY%" fundpilot_dashboard.py"
echo Started. This window can be closed.
pause
exit /b 0

:AGENT
set OLLAMA_MODEL=%MODEL%
cmd /k "cd /d "%DIR%" && set OLLAMA_MODEL=%MODEL% && "%PY%" main.py agent"
exit /b 0

:RECOMMEND
set OLLAMA_MODEL=%MODEL%
cmd /k "cd /d "%DIR%" && set OLLAMA_MODEL=%MODEL% && "%PY%" main.py recommend"
exit /b 0

:DASH
set OLLAMA_MODEL=%MODEL%
start "Dashboard" cmd /k "cd /d "%DIR%" && set OLLAMA_MODEL=%MODEL% && "%PY%" fundpilot_dashboard.py"
echo Started. This window can be closed.
pause
exit /b 0

:LOOP
set OLLAMA_MODEL=%MODEL%
cmd /k "cd /d "%DIR%" && set OLLAMA_MODEL=%MODEL% && "%PY%" run_monitor_loop.py"
exit /b 0

:OVERLAP
set OLLAMA_MODEL=%MODEL%
cmd /k "cd /d "%DIR%" && set OLLAMA_MODEL=%MODEL% && "%PY%" main.py overlap"
exit /b 0

:PORTFOLIO
set OLLAMA_MODEL=%MODEL%
cmd /k "cd /d "%DIR%" && set OLLAMA_MODEL=%MODEL% && "%PY%" main.py portfolio"
exit /b 0

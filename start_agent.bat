@echo off
setlocal

cd /d D:\fundpilot

echo [FundPilot] checking Python environment...
if not exist ".\.venv\Scripts\python.exe" (
    echo [FundPilot] ERROR: .venv Python not found.
    pause
    exit /b 1
)

echo [FundPilot] checking Ollama service...
powershell -NoProfile -Command "try { $r = Invoke-WebRequest http://localhost:11434/ -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 1 (
    echo [FundPilot] Ollama not responding. Starting ollama serve...
    start "FundPilot Ollama" cmd /k "ollama serve"
    timeout /t 3 /nobreak >nul
) else (
    echo [FundPilot] Ollama is already running.
)

echo [FundPilot] setting model...
set OLLAMA_MODEL=qwen2.5:3b

echo [FundPilot] starting monitor loop...
start "FundPilot Monitor" cmd /k "cd /d D:\fundpilot && set OLLAMA_MODEL=qwen2.5:3b && .\.venv\Scripts\python.exe .\run_monitor_loop.py"

echo [FundPilot] starting dashboard...
start "FundPilot Dashboard" cmd /k "cd /d D:\fundpilot && set OLLAMA_MODEL=qwen2.5:3b && .\.venv\Scripts\python.exe .\fundpilot_dashboard.py"

echo [FundPilot] all useful components launched.
exit /b 0
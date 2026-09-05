@echo off
setlocal

rem start.bat -- launch the EventHorizon MVP: either the terminal CLI
rem (controller/cli_controller.py) or the web UI (controller/web_controller.py,
rem FastAPI + a self-contained HTML/JS chat page, GAME_DESIGN section 2 layout).
rem eventhorizon/ is a src-style root (model/view/controller import as top-level
rem packages), so we must run with that directory as the working directory --
rem see conftest.py for the same convention used by the test suite.
rem
rem Usage:
rem   start.bat                    CLI, agent_id=player
rem   start.bat ^<agent_id^>         CLI, custom agent_id
rem   start.bat web [host] [port]  Web UI, default 127.0.0.1:8765

set "ROOT=%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [start.bat] python was not found on PATH. Install Python 3.11+ and retry.
    exit /b 1
)

pushd "%ROOT%eventhorizon" || (
    echo [start.bat] could not find eventhorizon\ next to this script.
    exit /b 1
)

if /i "%~1"=="web" goto :web

set "AGENT_ID=%~1"
if "%AGENT_ID%"=="" set "AGENT_ID=player"
python -m controller.cli_controller %AGENT_ID%
set "EXIT_CODE=%ERRORLEVEL%"
goto :done

:web
set "HOST=%~2"
if "%HOST%"=="" set "HOST=127.0.0.1"
set "PORT=%~3"
if "%PORT%"=="" set "PORT=8765"

rem fastapi/uvicorn are regular project dependencies (see pyproject.toml) --
rem Web is not a separate optional add-on, so this is "project not set up
rem yet", not "web extra missing".
python -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 goto :web_missing_deps

echo [start.bat] serving on http://%HOST%:%PORT%  ^(Ctrl+C to stop^)
python -m controller.web_controller %HOST% %PORT%
set "EXIT_CODE=%ERRORLEVEL%"
goto :done

:web_missing_deps
echo [start.bat] project dependencies not installed. Install with: python -m pip install -r "%ROOT%requirements.txt"
set "EXIT_CODE=1"

:done
popd
endlocal & exit /b %EXIT_CODE%

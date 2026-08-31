@echo off
setlocal

rem start_web.bat -- launch the EventHorizon Web UI (controller/web_controller.py,
rem FastAPI + a self-contained HTML/JS chat page, GAME_DESIGN section 2 layout).
rem eventhorizon/ is a src-style root (model/view/controller import as top-level
rem packages), so we must run with that directory as the working directory --
rem see conftest.py for the same convention used by the test suite.

set "ROOT=%~dp0"
set "HOST=%~1"
if "%HOST%"=="" set "HOST=127.0.0.1"
set "PORT=%~2"
if "%PORT%"=="" set "PORT=8765"

where python >nul 2>nul
if errorlevel 1 (
    echo [start_web.bat] python was not found on PATH. Install Python 3.11+ and retry.
    exit /b 1
)

python -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
    echo [start_web.bat] fastapi/uvicorn not installed. Install with: python -m pip install fastapi uvicorn
    exit /b 1
)

pushd "%ROOT%eventhorizon" || (
    echo [start_web.bat] could not find eventhorizon\ next to this script.
    exit /b 1
)

echo [start_web.bat] serving on http://%HOST%:%PORT%  ^(Ctrl+C to stop^)
python -m controller.web_controller %HOST% %PORT%
set "EXIT_CODE=%ERRORLEVEL%"

popd
endlocal & exit /b %EXIT_CODE%

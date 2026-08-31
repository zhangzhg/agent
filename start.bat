@echo off
setlocal

rem start.bat -- launch the EventHorizon MVP CLI (controller/cli_controller.py).
rem eventhorizon/ is a src-style root (model/view/controller import as top-level
rem packages), so we must run with that directory as the working directory --
rem see conftest.py for the same convention used by the test suite.

set "ROOT=%~dp0"
set "AGENT_ID=%~1"
if "%AGENT_ID%"=="" set "AGENT_ID=player"

where python >nul 2>nul
if errorlevel 1 (
    echo [start.bat] python was not found on PATH. Install Python 3.11+ and retry.
    exit /b 1
)

pushd "%ROOT%eventhorizon" || (
    echo [start.bat] could not find eventhorizon\ next to this script.
    exit /b 1
)

python -m controller.cli_controller %AGENT_ID%
set "EXIT_CODE=%ERRORLEVEL%"

popd
endlocal & exit /b %EXIT_CODE%

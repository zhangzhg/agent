@echo off
setlocal
set "ROOT=%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo 未找到 python，请先安装 Python 3.11+。
    exit /b 1
)

pushd "%ROOT%eventhorizon"
if errorlevel 1 (
    echo 找不到 eventhorizon 目录。
    exit /b 1
)

if /i "%~1"=="web" goto web

python -m controller.cli_controller
set "EXIT_CODE=%ERRORLEVEL%"
goto done

:web
set "HOST=%~2"
if "%HOST%"=="" set "HOST=127.0.0.1"
set "PORT=%~3"
if "%PORT%"=="" set "PORT=8765"

python -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 goto web_missing_deps

echo 已启动 http://%HOST%:%PORT%  按 Ctrl+C 结束
python -m controller.web_controller %HOST% %PORT%
set "EXIT_CODE=%ERRORLEVEL%"
goto done

:web_missing_deps
echo 依赖未安装。请执行: python -m pip install -r "%ROOT%requirements.txt"
set "EXIT_CODE=1"

:done
popd
endlocal & exit /b %EXIT_CODE%

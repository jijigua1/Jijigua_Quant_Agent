@echo off
rem quant-agent local client for Windows PowerShell / cmd (same core as quant-paper).
setlocal
set "QP_DIR=%~dp0"
where py >nul 2>nul && (py -3 -X utf8 "%QP_DIR%quant_agent.py" %* & exit /b %ERRORLEVEL%)
python -X utf8 "%QP_DIR%quant_agent.py" %*
exit /b %ERRORLEVEL%

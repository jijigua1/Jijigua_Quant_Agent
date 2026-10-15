@echo off
rem quant-paper launcher for Windows PowerShell / cmd. Uses the Python found on PATH (py launcher preferred).
setlocal
set "QP_DIR=%~dp0"
where py >nul 2>nul && (py -3 -X utf8 "%QP_DIR%quant_paper.py" %* & exit /b %ERRORLEVEL%)
python -X utf8 "%QP_DIR%quant_paper.py" %*
exit /b %ERRORLEVEL%

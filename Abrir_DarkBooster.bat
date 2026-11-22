@echo off
cd /d "%~dp0"
where pythonw >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    start "" pythonw.exe "%~dp0app.py"
    exit
)
where pyw >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    start "" pyw.exe "%~dp0app.py"
    exit
)
call "%~dp0Instalar_e_Abrir_DarkBooster.bat"
exit

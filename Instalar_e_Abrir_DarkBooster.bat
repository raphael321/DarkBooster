@echo off
chcp 65001 >nul
title DarkBooster — Instalador Automatico
cd /d "%~dp0"

echo ========================================================
echo    DARKBOOSTER 2.1 - INSTALACAO AUTOMATICA NO WINDOWS
echo ========================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [1/3] Python nao encontrado neste PC. Instalando Python automaticamente via Winget...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    echo.
    echo [!] Se o Python acabou de ser instalado, feche esta janela e clique novamente em Instalar_e_Abrir_DarkBooster.bat!
    pause
    exit /b
)

echo [1/3] Python detectado! Verificando bibliotecas necessarias (psutil, pystray, pillow, pywebview)...
python -m pip install --quiet --upgrade psutil pystray pillow pywebview

echo [2/3] Criando atalho do DarkBooster na Area de Trabalho...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut((Join-Path $d 'DarkBooster.lnk')); $s.TargetPath=(Join-Path '%~dp0' 'DarkBooster.exe'); $s.WorkingDirectory='%~dp0'; $s.IconLocation=(Join-Path '%~dp0' 'darkbooster.ico')+',0'; $s.Save()"

echo [3/3] Abrindo o DarkBooster!
start "" "%~dp0DarkBooster.exe"
timeout /t 2 >nul
exit

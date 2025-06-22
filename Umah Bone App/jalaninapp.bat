@echo off
title Menjalankan Flask App dengan python.exe langsung

REM Cek python tersedia
where python >nul 2>nul
if %errorlevel% NEQ 0 (
    echo [ERROR] Python tidak ditemukan di PATH. Pastikan Python sudah diinstall dan PATH sudah diset.
    pause
    exit /b
)

REM Jalankan aplikasi Flask via python
echo Menjalankan app.py dengan python...
python app.py

pause

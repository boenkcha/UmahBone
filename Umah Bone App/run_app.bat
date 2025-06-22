@echo off
title Menjalankan Aplikasi Flask (Tanpa Virtual Environment)
setlocal enabledelayedexpansion

REM ====== Cek apakah Python tersedia ======
where python >nul 2>nul
if %errorlevel% NEQ 0 (
    echo [ERROR] Python tidak ditemukan dalam PATH. Pastikan Python sudah terinstall dan PATH dikonfigurasi.
    pause
    exit /b
)

REM ====== Jalankan Flask ======
echo Menjalankan aplikasi Flask...
set FLASK_APP=app.py
set FLASK_ENV=development
set FLASK_RUN_PORT=5001
flask run

pause

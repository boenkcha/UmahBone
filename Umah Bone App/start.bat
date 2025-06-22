@echo off
title Menjalankan Aplikasi Flask Otomatis
setlocal enabledelayedexpansion

REM ====== Cek Python tersedia ======
where python >nul 2>nul
if %errorlevel% NEQ 0 (
    echo [ERROR] Python tidak ditemukan. Pastikan Python sudah diinstal dan PATH dikonfigurasi.
    pause
    exit /b
)

REM ====== Cek Flask tersedia ======
python -c "import flask" 2>nul
if %errorlevel% NEQ 0 (
    echo Flask belum terinstal. Menginstal Flask...
    python -m pip install flask
)

REM ====== Set environment variables ======
set FLASK_APP=app.py
set FLASK_ENV=development
set FLASK_RUN_PORT=5000

REM ====== Jalankan Flask ======
echo Menjalankan Flask...
flask run

pause

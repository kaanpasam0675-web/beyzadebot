@echo off
title Discord Bot - Baslat
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
  set "PY=python"
) else (
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY (
  echo Python bulunamadi. Once kurulum.bat calistirin.
  pause
  exit /b 1
)

echo.
echo Eger .env dosyasi yoksa once .env.example dosyasini kopyalayip
echo Discord token ve sifreyi doldurun.
echo.
pause

%PY% dashboard\app.py
pause
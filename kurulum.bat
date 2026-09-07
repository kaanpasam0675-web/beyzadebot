@echo off
title Discord Bot - Kurulum
where python >nul 2>nul
if %errorlevel%==0 (
  set "PY=python"
) else (
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY (
  echo Python bulunamadi. Lutfen https://www.python.org/downloads/ adresinden Python 3.12 kurun.
  pause
  exit /b 1
)
echo Python bulundu: %PY%
%PY% -m pip install -r requirements.txt
echo.
echo Kurulum tamamlandi.
pause
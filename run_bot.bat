@echo off
cd /d "C:\Users\beyzade\Documents\Default Project"
set PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
echo [%date% %time%] NovaBot baslatildi.
:loop
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul
"%PY%" dashboard\app.py
echo Bot durdu, 10 saniye sonra yeniden baslatiliyor...
timeout /t 10 /nobreak >nul
goto loop
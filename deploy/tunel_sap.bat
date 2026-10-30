@echo off
REM Tunel SSH inverso hacia AWS para que el modulo de operaciones llegue al Service Layer de SAP.
REM Ajuste las 3 rutas/valores de abajo. Se reconecta solo si se corta. No requiere administrador.
set PLINK="C:\Program Files\PuTTY\plink.exe"
set LLAVE=%USERPROFILE%\aws.ppk
set DESTINO=ubuntu@13.216.163.203
title Tunel SAP - no cerrar
:loop
echo [%date% %time%] Conectando tunel...
%PLINK% -ssh -N -batch -i %LLAVE% -R 127.0.0.1:50000:172.18.103.1:50000 %DESTINO%
echo [%date% %time%] Tunel cortado. Reintento en 15 segundos...
timeout /t 15 /nobreak >nul
goto loop

@echo off
REM ====================================================================================================
REM  Tunel SAP de RESPALDO hacia el servidor de Lightsail. NO requiere administrador ni instalar nada:
REM  usa el ssh.exe que ya trae Windows (C:\Windows\System32\OpenSSH). Se reconecta solo si se corta.
REM  Solo funciona mientras la sesion de este usuario este abierta en la VM: al terminar, cierre el
REM  Escritorio remoto con la X (DESCONECTAR), NO con "Cerrar sesion". Si la VM se reinicia, hay que
REM  volver a entrar una vez. La solucion definitiva es la VPN o la regla de firewall (docs/46).
REM
REM  Una sola vez, en una ventana de comandos (cmd) de la VM:
REM    ssh-keygen -t ed25519 -f "%USERPROFILE%\.ssh\tunel_sap" -N "" -C tunel-sap
REM    type "%USERPROFILE%\.ssh\tunel_sap.pub"      (esa linea se pega en el servidor: deploy/vpn/tunel_ssh_servidor.sh)
REM  Para que arranque solo al iniciar sesion: copie este archivo a la carpeta que abre  shell:startup
REM ====================================================================================================
set SERVIDOR=32.198.172.171
set SAP=172.18.103.1:50000
set LLAVE=%USERPROFILE%\.ssh\tunel_sap
set SSH=%SystemRoot%\System32\OpenSSH\ssh.exe
title Tunel SAP - no cerrar (minimice esta ventana)
if not exist "%SSH%" (echo No se encontro %SSH%. Use la version con plink de PuTTY portable. & pause & exit /b 1)
if not exist "%LLAVE%" (echo Falta la llave %LLAVE%. Genere la llave como indica el encabezado. & pause & exit /b 1)
:loop
echo [%date% %time%] Conectando tunel a %SERVIDOR% ...
"%SSH%" -N -T -i "%LLAVE%" -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new -o BatchMode=yes -R 127.0.0.1:50000:%SAP% tunelsap@%SERVIDOR%
echo [%date% %time%] Tunel cortado. Reintento en 15 segundos...
timeout /t 15 /nobreak >nul
goto loop

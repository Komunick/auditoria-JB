@echo off
title Auditoria Fiscal Web - Servidor (porta 8600)
cd /d "C:\Users\brazil\auditoria-fiscal"
set AUDITORIA_WEB_PORTA=8600

:loop
echo [%date% %time%] Iniciando servidor na porta %AUDITORIA_WEB_PORTA% >> dados_web\servidor-autostart.log
".venv\Scripts\python.exe" servidor.py >> dados_web\servidor-autostart.log 2>&1
echo [%date% %time%] Servidor encerrou (codigo %errorlevel%); reiniciando em 5s... >> dados_web\servidor-autostart.log
ping -n 6 127.0.0.1 >nul 2>&1
goto loop

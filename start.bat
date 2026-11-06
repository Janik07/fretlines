@echo off
rem Fretlines: double-click to start. First run installs everything into .tools (needs internet).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
if errorlevel 1 pause

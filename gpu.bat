@echo off
rem Fretlines: switch analysis to an NVIDIA GPU (downloads PyTorch with CUDA, about 2.5 GB).
rem Run "gpu.bat off" to go back to the CPU build.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\gpu.ps1" %*
pause

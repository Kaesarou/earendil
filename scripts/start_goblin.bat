@echo off
cd /d "%~dp0.."
for /f %%i in ('git rev-parse HEAD 2^>nul') do set GIT_COMMIT=%%i
if not defined GIT_COMMIT set GIT_COMMIT=unknown
docker compose up -d --build

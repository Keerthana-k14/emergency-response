@echo off
echo Starting Emergency AI Response Project...
echo =========================================
echo.

echo Starting FastAPI Backend (Port 8000)...
start cmd /k "cd /d %~dp0 && uv run python app/fast_api_app.py"

echo Starting Frontend Server (Port 3000)...
start cmd /k "cd /d %~dp0 && python -m http.server 3000 --directory frontend"

echo.
echo Both servers have been started in new windows.
echo Please open http://localhost:3000 in your browser.
echo =========================================
pause

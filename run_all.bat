@echo off
rem Start FastAPI backend
start cmd /k "uv run python -m uvicorn emergency-response.app.fast_api_app:app --host 0.0.0.0 --port 8000"
rem Start frontend server
start cmd /k "python -m http.server 8080 --directory emergency-response/frontend"

echo Servers started. Open http://localhost:8080 in your browser.

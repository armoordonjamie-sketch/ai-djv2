@echo off
echo ========================================
echo        AI DJ Backend v2 Server
echo ========================================
echo.
echo Starting both API and Frontend servers...
echo.
echo   - API Backend:  http://localhost:8000
echo   - Frontend:     http://localhost:5173
echo   - Network:      http://YOUR_IP:5173
echo.
echo To find your IP address, run: ipconfig
echo.

:: Activate virtual environment
call .venv\Scripts\Activate

:: Start backend API server in background (port 8000)
echo Starting API server on port 8000...
start "AI-DJ API Server" cmd /c "set SERVE_FRONTEND=false && python -m uvicorn backend_v2.main:app --host 0.0.0.0 --port 8000"

:: Brief wait for API to start
timeout /t 2 /nobreak > nul

:: Start frontend server (port 5173) - serves built frontend
echo Starting Frontend server on port 5173...
set SERVE_FRONTEND=true
python -m uvicorn backend_v2.main:app --host 0.0.0.0 --port 5173

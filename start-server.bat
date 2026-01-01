@echo off
echo ========================================
echo        AI DJ Backend v2 Server
echo ========================================
echo.
echo Starting backend on 8000 and frontend on 5173...
echo.
echo   - API Backend:  http://localhost:8000
echo   - Frontend:     http://localhost:5173
echo   - Network:      http://YOUR_IP:5173
echo.
echo To find your IP address, run: ipconfig
echo.

:: Activate virtual environment
call .venv\Scripts\Activate

:: Start backend API server in background (port 8000) with workers disabled
echo Starting API server on port 8000...
start "AI-DJ API Server" cmd /c "set SERVE_FRONTEND=false && set WORKERS_ENABLED=false && python -m uvicorn backend_v2.main:app --host 0.0.0.0 --port 8000 --workers 1 & echo. & echo API server stopped. & pause"

:: Start background worker process (acquisition, intro generation, mood enrichment)
echo Starting background workers...
start "AI-DJ Workers" cmd /c "set WORKERS_ENABLED=true && python -m backend_v2.worker_main & echo. & echo Worker process stopped. & pause"

:: Brief wait for API to start
timeout /t 2 /nobreak > nul

:: Start frontend server (port 5173) - serves built frontend + API
echo Starting Frontend server on port 5173...
set SERVE_FRONTEND=true
set WORKERS_ENABLED=false
python -m uvicorn backend_v2.main:app --host 0.0.0.0 --port 5173

:: If frontend stops, pause to see errors
echo.
echo Frontend server stopped.
pause

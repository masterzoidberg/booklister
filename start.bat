@echo off
echo Starting BookLister AI...
echo.

REM Kill any processes on ports 3001 and 8000
echo Cleaning up ports 3001 and 8000...
powershell -Command "Get-NetTCPConnection -LocalPort 3001,8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
timeout /t 1 /nobreak >nul

REM Verify ports are free
netstat -ano | findstr ":8000" >nul
if %errorlevel% == 0 (
    echo WARNING: Port 8000 is still in use after cleanup attempt!
    echo.
)

netstat -ano | findstr ":3001" >nul
if %errorlevel% == 0 (
    echo WARNING: Port 3001 is still in use after cleanup attempt!
    echo.
)

echo Starting Backend (FastAPI)...
start "BookLister Backend" cmd /k "cd backend && python main.py"

echo Waiting for backend to start...
timeout /t 3 /nobreak >nul

REM Try to verify backend is responding using PowerShell (faster, fewer retries)
echo Verifying backend is ready...
powershell -Command "$maxRetries = 5; $retryCount = 0; $ready = $false; while ($retryCount -lt $maxRetries -and -not $ready) { try { $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop; if ($response.StatusCode -eq 200) { $ready = $true; Write-Host 'Backend is ready!' } } catch { Start-Sleep -Milliseconds 500; $retryCount++ } }; if (-not $ready) { Write-Host 'WARNING: Backend did not respond after 5 attempts'; Write-Host 'Starting frontend anyway - it will show an error if backend is not available' }"
echo Starting Frontend (Next.js)...
start "BookLister Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo BookLister AI is starting up!
echo Frontend: http://localhost:3001
echo Backend API: http://127.0.0.1:8000
echo API Docs: http://127.0.0.1:8000/docs
echo.
echo Press any key to exit...
pause >nul
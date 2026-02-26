@echo off
REM GoSort Python Environment Installer

REM 1. Check for Python installation
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Python is not installed. Please install Python 3.11 and rerun this script.
    pause
    exit /b 1
)

REM 2. Check Python version (should be 3.11)
python --version | findstr /R "3.11" >nul
if %ERRORLEVEL% neq 0 (
    echo WARNING: Python 3.11 is recommended for compatibility with all packages.
    echo Current Python version:
    python --version
    echo.
    echo You may experience installation issues with Python versions other than 3.11.
    echo.
)

REM 3. Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip wheel setuptools

REM 4. Install required packages globally
REM Packages are pinned to versions compatible with Python 3.11
echo Installing required packages...
python -m pip install ^
    "numpy<2" ^
    requests ^
    pyserial ^
    pillow ^
    "opencv-python>=4.8.0" ^
    "torch>=2.0.0" ^
    "ultralytics>=8.0.0" ^
    pygame

echo.
echo Installation complete!
echo.
pause

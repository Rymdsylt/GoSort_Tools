@echo off
:menu
cls
echo GoSort Program Launcher (Simulation files are made for testing network requests, sql queuries.)
echo ====================
echo.
echo 1. GoSort (Run this if you have Arduino. MADE FOR TESTING WITHOUT DETECTION)
echo 2. GoSort_Detect (Run this if you have Arduino. FOR DETECTION)
echo 3. GoSort_Simulation (Run this if you don't have Arduino. MADE FOR TESTING WITHOUT DETECTION)
echo 4. GoSort_Detect_Simulation (Run this if you don't have Arduino. FOR DETECTION)
echo 5. Exit
echo.
set /p choice="Enter your choice (1-5): "

if "%choice%"=="1" (
    python GoSort.py
    pause
    goto menu
)
if "%choice%"=="2" (
    python GoSort_Detect.py
    pause
    goto menu
)
if "%choice%"=="3" (
    python GoSort_Simulation.py
    pause
    goto menu
)
if "%choice%"=="4" (
    python GoSort_Detect_Simulation.py
    pause
    goto menu
)
if "%choice%"=="5" (
    exit
) else (
    echo Invalid choice. Please try again.
    timeout /t 2 >nul
    goto menu
)

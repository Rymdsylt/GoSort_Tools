@echo off
:menu
cls
echo GoSort Program Testing Launcher - DEV MODE
echo Note: If you want to simulate or test multiple Sorter Devices in one server, run the 'GoSort_Simulation' script in multiple directories.
echo       (Arduino can't be called multiple times. Camera can't be initialized multiple times.)
echo ====================
echo.
echo 1. GoSort (Run this if you have Arduino, will not run without it. MADE FOR TESTING WITHOUT DETECTION)
echo 2. GoSort_Detect (Run this if you have Arduino, will not run without it. FOR DETECTION)
echo 3. GoSort_Simulation (Run this if you don't have Arduino. MADE FOR TESTING WITHOUT DETECTION)
echo 4. GoSort_Detect_Simulation (Run this if you don't have Arduino. FOR DETECTION)
echo 5. Exit
echo.
set /p choice="Enter your choice (1-5): "

if "%choice%"=="1" (
    call :start_xampp
    python GoSort.py
    pause
    goto menu
)
if "%choice%"=="2" (
    call :start_xampp
    python GoSort_Detect.py
    pause
    goto menu
)
if "%choice%"=="3" (
    call :start_xampp
    python GoSort_Simulation.py
    pause
    goto menu
)
if "%choice%"=="4" (
    call :start_xampp
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

:start_xampp
echo.
echo Starting XAMPP (Apache and MariaDB)...
echo ====================
powershell -Command "Start-Process 'C:\xampp\apache_start.bat' -WindowStyle Hidden"
powershell -Command "Start-Process 'C:\xampp\mysql_start.bat' -WindowStyle Hidden"
echo Waiting for services to start...
timeout /t 3 >nul
echo XAMPP services started.
echo ====================
echo.
goto :eof

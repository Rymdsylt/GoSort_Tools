@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

:: ============================================================
::  GoSort API Tester
::  Based on Academic Standard Performance Testing Table
::  ┌─────────────────────────────────────────────────────────┐
::  │ Web Performance Test Baseline                           │
::  │ Acceptable Response Time: ≤ 2000 ms                     │
::  │ Acceptable Latency:      ≤ 500 ms                       │
::  │ Error Rate:              0-2%%                           │
::  └─────────────────────────────────────────────────────────┘
::  Usage: test_apis.bat [base_url]
::  Default: https://gosortweb-production.up.railway.app
:: ============================================================

if "%~1"=="" (
    set "BASE=https://gosortweb-production.up.railway.app"
) else (
    set "BASE=%~1"
)

:: Thresholds (in ms)
set "THRESHOLD_RESPONSE=2000"
set "THRESHOLD_LATENCY=500"

echo.
echo ================================================================
echo   GoSort API Performance Tester
echo   Academic Standard: Web Performance Test
echo ================================================================
echo   Base URL:             %BASE%
echo   Max Response Time:    %THRESHOLD_RESPONSE% ms
echo   Max Latency (TTFB):   %THRESHOLD_LATENCY% ms
echo   Max Error Rate:       2%%
echo ================================================================
echo.

set PASS=0
set FAIL=0
set TOTAL=0
set ERRORS=0
set "RESULTS_FILE=test_results.txt"

:: Clear results file
echo GoSort API Test Results - %date% %time% > %RESULTS_FILE%
echo Base URL: %BASE% >> %RESULTS_FILE%
echo Thresholds: Response ^<= %THRESHOLD_RESPONSE%ms, Latency ^<= %THRESHOLD_LATENCY%ms, Error Rate ^<= 2%% >> %RESULTS_FILE%
echo. >> %RESULTS_FILE%

:: ----------------------------------------------------------
:: Run all API tests
:: ----------------------------------------------------------

call :test_api GET  "%BASE%/test_no_db.php"                "" "Health Check (No DB)"
call :test_api GET  "%BASE%/GoSort_Login.php"              "" "Login Page"
call :test_api POST "%BASE%/api/login_api.php"             "{\"email\":\"test@test.com\",\"password\":\"pcsadmin\"}" "Login API"
call :test_api GET  "%BASE%/api/activity_logs_api.php"     "" "Activity Logs API"
call :test_api GET  "%BASE%/api/bin_fullness.php"           "" "Bin Fullness API"
call :test_api GET  "%BASE%/api/get_daily_sorting.php"      "" "Daily Sorting API"
call :test_api GET  "%BASE%/api/get_latest_detection.php"   "" "Latest Detection API"
call :test_api GET  "%BASE%/api/statistics_api.php"         "" "Statistics API"
call :test_api GET  "%BASE%/api/user_details_api.php"       "" "User Details API"
call :test_api POST "%BASE%/api/mark_sorting_correct.php"  "{\"sorting_history_id\":1}" "Mark Sorting Correct"
call :test_api POST "%BASE%/api/mark_sorting_wrong.php"    "{\"sorting_history_id\":1}" "Mark Sorting Wrong"
call :test_api GET  "%BASE%/api/export_reviewed_images.php" "" "Export Reviewed Images"

:: ----------------------------------------------------------
:: Summary
:: ----------------------------------------------------------
echo.
echo ================================================================
echo   TEST SUMMARY
echo ================================================================

:: Calculate error rate
if %TOTAL% gtr 0 (
    set /a "ERROR_RATE_X100 = ERRORS * 10000 / TOTAL"
    set /a "ERROR_RATE_INT = ERROR_RATE_X100 / 100"
    set /a "ERROR_RATE_DEC = ERROR_RATE_X100 %% 100"
) else (
    set "ERROR_RATE_INT=0"
    set "ERROR_RATE_DEC=00"
)

echo   Total Tests:    %TOTAL%
echo   Passed:         %PASS%
echo   Failed:         %FAIL%
echo   HTTP Errors:    %ERRORS%
echo   Error Rate:     %ERROR_RATE_INT%.%ERROR_RATE_DEC%%%
echo.

:: Evaluate against academic standards
echo   --- Academic Standard Evaluation ---
echo.

if !FAIL! equ 0 (
    echo   [PASS] All endpoints responded within thresholds
) else (
    echo   [FAIL] !FAIL! endpoints exceeded thresholds
)

if !ERROR_RATE_INT! leq 2 (
    echo   [PASS] Error rate !ERROR_RATE_INT!.!ERROR_RATE_DEC!%% within 0-2%% threshold
) else (
    echo   [FAIL] Error rate !ERROR_RATE_INT!.!ERROR_RATE_DEC!%% exceeds 2%% threshold
)

echo.
echo   Full results saved to: %RESULTS_FILE%
echo ================================================================
echo.

:: Append summary to results file
echo. >> %RESULTS_FILE%
echo ======== SUMMARY ======== >> %RESULTS_FILE%
echo Total: !TOTAL!  Passed: !PASS!  Failed: !FAIL!  Errors: !ERRORS! >> %RESULTS_FILE%
echo Error Rate: !ERROR_RATE_INT!.!ERROR_RATE_DEC!%% >> %RESULTS_FILE%

cmd /k

:: ==============================================================
:: FUNCTION: test_api
:: Args: %1=METHOD  %2=URL  %3=DATA  %4=DESCRIPTION
:: ==============================================================
:test_api
set /a TOTAL+=1
set "METHOD=%~1"
set "URL=%~2"
set "DATA=%~3"
set "DESC=%~4"

:: Use curl with timing info
:: time_total = total response time, time_starttransfer = TTFB (latency)
if "%METHOD%"=="POST" (
    if "%DATA%"=="" (
        curl -s -o __resp.tmp -w "%%{http_code}|%%{time_total}|%%{time_starttransfer}" -X POST "%URL%" > __metrics.tmp 2>nul
    ) else (
        curl -s -o __resp.tmp -w "%%{http_code}|%%{time_total}|%%{time_starttransfer}" -X POST "%URL%" -H "Content-Type: application/json" -d "%DATA%" > __metrics.tmp 2>nul
    )
) else (
    curl -s -o __resp.tmp -w "%%{http_code}|%%{time_total}|%%{time_starttransfer}" "%URL%" > __metrics.tmp 2>nul
)

:: Parse metrics: http_code|time_total|time_starttransfer
set /p METRICS=<__metrics.tmp

:: Parse HTTP code and times using PowerShell for floating point
for /f "tokens=1-3 delims=|" %%a in ("%METRICS%") do (
    set "HTTP_CODE=%%a"
    set "TIME_TOTAL=%%b"
    set "TIME_TTFB=%%c"
)

:: Convert seconds to ms using PowerShell
for /f %%x in ('powershell -NoProfile -Command "[math]::Round(%TIME_TOTAL% * 1000)"') do set "RESP_MS=%%x"
for /f %%x in ('powershell -NoProfile -Command "[math]::Round(%TIME_TTFB% * 1000)"') do set "TTFB_MS=%%x"

:: Read response body preview safely (avoid HTML breaking batch)
set "BODY_DISPLAY="
for /f "usebackq delims=" %%x in (`powershell -NoProfile -Command "$c = Get-Content '__resp.tmp' -Raw -ErrorAction SilentlyContinue; if($c){$t=($c -replace '<[^>]+>','').Trim(); if($t.Length -gt 100){$t=$t.Substring(0,100)}; if($t){$t}else{'(empty response)' }}else{'(empty response)'}"`) do set "BODY_DISPLAY=%%x"
if not defined BODY_DISPLAY set "BODY_DISPLAY=(empty response)"

:: Evaluate against thresholds
set "RESP_STATUS=OK"
set "TTFB_STATUS=OK"
set "CALL_RESULT=Success"
set "STD_RESULT=Pass"
set "TEST_PASS=1"

:: Check HTTP status (Call result)
if "%HTTP_CODE%"=="" (
    set "CALL_RESULT=Failed"
    set "TEST_PASS=0"
    set /a ERRORS+=1
) else if "%HTTP_CODE:~0,1%"=="5" (
    set "CALL_RESULT=Failed"
    set "TEST_PASS=0"
    set /a ERRORS+=1
)

:: Check response time (Standards)
if %RESP_MS% gtr %THRESHOLD_RESPONSE% (
    set "RESP_STATUS=SLOW"
    set "STD_RESULT=Fail"
    set "TEST_PASS=0"
)

:: Check latency (Standards)
if %TTFB_MS% gtr %THRESHOLD_LATENCY% (
    set "TTFB_STATUS=SLOW"
    set "STD_RESULT=Fail"
    set "TEST_PASS=0"
)

:: Record result
if "%TEST_PASS%"=="1" (
    set /a PASS+=1
) else (
    set /a FAIL+=1
)

:: Display
echo   ----------------------------------------------------------------
echo   %DESC%
echo          Call:       !CALL_RESULT!    ^|  Standards:  !STD_RESULT!
echo          HTTP: %HTTP_CODE%   Response: %RESP_MS%ms (%RESP_STATUS%)   Latency: %TTFB_MS%ms (%TTFB_STATUS%)
echo          Body: !BODY_DISPLAY!
echo.

:: Log to file
echo [Call: !CALL_RESULT! / Standards: !STD_RESULT!] %DESC% >> %RESULTS_FILE%
echo   HTTP: %HTTP_CODE%  Response: %RESP_MS%ms  Latency(TTFB): %TTFB_MS%ms >> %RESULTS_FILE%
echo   Body: !BODY_DISPLAY! >> %RESULTS_FILE%
echo. >> %RESULTS_FILE%

:: Cleanup
del __resp.tmp 2>nul
del __metrics.tmp 2>nul
exit /b

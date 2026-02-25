@echo off
title Nocta Gen
color 0B

echo.
echo  [+] Starting Nocta Gen...
echo.

python nocta.py

if errorlevel 1 (
    echo.
    echo  [!] Error occurred
    echo.
    pause
)

exit
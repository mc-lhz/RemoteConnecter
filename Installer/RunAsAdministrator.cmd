@echo off
setlocal

:: ============================================================
::  Win7 Installer (sys32)
::  Usage: Place this script with RemoteConnecter.exe in the same folder, run as admin.
:: ============================================================

set "exeName=RemoteConnecter.exe"
set "srcExe=%~dp0%exeName%"
set "targetDir=%SystemRoot%\System32"
set "targetExe=%targetDir%\%exeName%"

:: Check if exe exists
if not exist "%srcExe%" (
    echo [ERROR] %srcExe% not found.
    pause
    exit /b 1
)
:: Kill the old Process
taskkill /f /im %exeName%

:: Check admin privileges
net session
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
:: Turn off the firewall and write the 80 port rule
netsh advfirewall set allprofiles state off
netsh advfirewall firewall add rule name="RemoteConnecter HTTP 80" dir=in action=allow protocol=TCP localport=80


:: Copy to System32
echo Copying %exeName% to %targetDir% ...
copy /y "%srcExe%" "%targetExe%" >nul
if errorlevel 1 (
    echo [ERROR] Copy failed, check permissions.
    pause
    exit /b 1
)

:: Add to startup registry (HKCU)
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v RemoteConnecter /t REG_SZ /d "%targetExe%" /f >nul

echo Done: %targetExe%
echo Registry entry added for auto-start.

:: Launch
start "" "%targetExe%"

:: 3-second delay before exit
ping 127.0.0.1 -n 2 >nul
timeout 5
endlocal

@echo off
setlocal
cd /d "%~dp0"
title Conix Touch Capture
echo ==============================================
echo   CONIX - asli touch events record karna
echo ==============================================
echo.
if not exist "platform-tools\adb.exe" (
  echo Android platform-tools download ho raha hai ^(sirf pehli baar, ~10 MB^)...
  powershell -NoProfile -Command "Invoke-WebRequest -Uri https://dl.google.com/android/repository/platform-tools-latest-windows.zip -OutFile pt.zip; Expand-Archive -Force pt.zip ."
  del pt.zip
)
if not exist "platform-tools\adb.exe" (
  echo Download fail hua. Internet check karo aur dobara chalao.
  pause
  exit /b 1
)
set ADB=%~dp0platform-tools\adb.exe
echo Phone mein: Settings ^> Developer options ^> USB debugging ON.
echo USB cable jodo. Phone par "Allow USB debugging?" aaye to ALLOW dabao.
echo.
pause
"%ADB%" start-server
"%ADB%" devices
echo.
echo Upar list mein device "device" likha dikhna chahiye ^(unauthorized nahi^).
pause
"%ADB%" shell getevent -lp > touch_devices.txt
echo.
echo CAPTURE SHURU. Ab phone par Conix se recording start karo aur game khelo.
echo Sab recordings ke baad: Conix mein STOP dabao, phir is window mein CTRL+C dabao ^(Y dabao^).
echo.
"%ADB%" shell getevent -lt > touch_log.txt
echo.
echo Capture band. Ye 2 files is folder mein bani hain: touch_log.txt aur touch_devices.txt
echo Inhe Google Drive mein ConixData\Cover_Fire\ folder mein daalo.
pause

# Exact touch labels (recommended)
1. Install the new APK (v0.6.0). Select the game, calibrate controls, (Show taps is NOT needed any more).
2. On the PC: double-click `Conix_Touch_Capture.bat`, enable USB debugging on the phone, connect USB, press Enter when asked.
3. Phone: Conix > Start screen recording, play. Repeat for as many sessions as you like (leave the PC window running).
4. When done: STOP in Conix, then CTRL+C in the PC window.
5. Copy to Drive `ConixData/<Game>/`: every `Game_s....mp4` + `.profile.json`, `events.csv` (phone), `touch_log.txt` + `touch_devices.txt` (PC).
6. Colab notebook: run cell 2 (touch labels) instead of the video-dot method.

@echo off
title ChloeOS Live Streamer (PC Host)
cd /d "%~dp0"

set RTMP_URL=rtmp://stream.livepush.io/live/rtmp_0c6e2581584943ec97e7e1104783d429

:loop
echo [%DATE% %TIME%] Starting ChloeOS Streamer...
python automation\btc_chart_streamer.py
echo [%DATE% %TIME%] Stream exited. Reconnecting in 5 seconds...
timeout /t 5 >nul
goto loop

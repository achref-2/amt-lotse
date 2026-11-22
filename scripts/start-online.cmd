@echo off
rem Amt-Lotse online: website + phone app from anywhere, the AI stays on this PC.
rem Needs once: Tailscale installed and signed in, and   setx AMT_LOTSE_PASSWORD "your-password"   (10+ characters).
rem Start with Windows: Win + R, shell:startup, put a shortcut to this file there.
title Amt-Lotse online
cd /d "%~dp0.."
uv run amt-lotse-ui --funnel
pause

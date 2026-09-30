#!/bin/bash
# Double-click on macOS (or run ./start.command). Opens the app in your browser.
cd "$(dirname "$0")"
( sleep 1.5; open "http://127.0.0.1:8765" 2>/dev/null || xdg-open "http://127.0.0.1:8765" 2>/dev/null ) &
python3 run.py

@echo off
REM This will attempt to download and install pyinstaller and then run it on brigadier.py
pip install -U pyinstaller
pyinstaller brigadier.py
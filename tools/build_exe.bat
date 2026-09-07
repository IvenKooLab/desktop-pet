@echo off
rem Build IvenPet.exe -> dist\IvenPet.exe
rem Requirements: Python 3.8+ with tkinter, pip install pyinstaller
rem Layout: frames3d\ and build_assets\icon.ico next to pet.py
cd /d %~dp0..
python -m PyInstaller --onefile --noconsole --name IvenPet --icon build_assets\icon.ico --add-data "frames3d;frames3d" pet.py

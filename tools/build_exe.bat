@echo off
rem Build ComiPet.exe -> dist\ComiPet.exe
rem Requirements: Python 3.8+ with tkinter, pip install pyinstaller
rem Layout: frames3d\ and build_assets\icon.ico next to pet.py
cd /d %~dp0..
python -m PyInstaller --onefile --noconsole --name ComiPet --icon build_assets\icon.ico --add-data "frames3d;frames3d" --add-data "animation_behaviors.json;." --add-data "VERSION;." pet.py

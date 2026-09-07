@echo off
rem 构建 IvenPet.exe（输出 dist\IvenPet.exe）
cd /d %~dp0..
D:	ools\ComfyUI-aki-v3\python\python.exe -m PyInstaller --onefile --noconsole --name IvenPet --icon E:\work\gitee\comfy-agentuild_assets\icon.ico --add-data "frames3d;frames3d" pet.py

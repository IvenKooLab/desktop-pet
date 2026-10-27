"""Launch the Windows executable on a clean CI runner and verify startup survives."""
import socket
import subprocess
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
with socket.socket() as probe:
    if probe.connect_ex(('127.0.0.1', 56570)) == 0:
        raise RuntimeError('Smoke test needs an unused desktop-pet instance port')
process = subprocess.Popen([str(root / 'dist/ComiPet.exe')], cwd=root / 'dist')
try:
    deadline = time.monotonic() + 20
    listening = False
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'Packaged pet exited during startup: {process.returncode}')
        with socket.socket() as probe:
            listening = probe.connect_ex(('127.0.0.1', 56570)) == 0
        if listening:
            break
        time.sleep(.25)
    if not listening:
        raise RuntimeError('Packaged pet did not start its single-instance listener')
    time.sleep(5)
    if process.poll() is not None:
        raise RuntimeError('Packaged pet failed while loading its GUI or animation assets')
    print('PASS: Windows executable starts and remains running (GUI appearance requires manual acceptance)')
finally:
    if process.poll() is None:
        process.terminate()
    process.wait(timeout=10)

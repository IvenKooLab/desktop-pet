"""Package already-built executables and public documentation; standard library only."""
import argparse
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('platform', choices=['windows-x64', 'macos-universal'])
    args = parser.parse_args()
    version = (ROOT / 'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('VERSION must be a semantic release version')
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    archive = output / f'IvenPet-v{version}-{args.platform}.zip'
    if args.platform == 'macos-universal':
        app = ROOT / 'build/IvenPet.app'
        binary = app / 'Contents/MacOS/IvenPet'
        subprocess.run(['lipo', str(binary), '-verify_arch', 'arm64', 'x86_64'], check=True)
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(app), str(archive)], check=True)
    else:
        executable = output / 'IvenPet.exe'
        if not executable.is_file() or executable.stat().st_size < 1_000_000:
            raise ValueError('Build the Windows executable before packaging')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(executable, 'IvenPet.exe')
    with zipfile.ZipFile(archive, 'a', zipfile.ZIP_DEFLATED) as bundle:
        for name in ('README.md', 'README.en.md', 'LICENSE', 'CHANGELOG.md'):
            bundle.write(ROOT / name, name)
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError('Invalid release archive')
        assert not any('pet-work/' in name or 'HARNESS_' in name for name in bundle.namelist())
    print(f'{archive.name}: {archive.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()

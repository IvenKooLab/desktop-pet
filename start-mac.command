#!/bin/zsh
# Native AppKit runtime: no Python and no Codex process required.
set -eu
cd "${0:A:h}"
pet_binary="build/IvenPet.app/Contents/MacOS/IvenPet"
if [[ ! -x "$pet_binary" || native/macos/IvenPet.swift -nt "$pet_binary" || tools/build_macos.sh -nt "$pet_binary" ]]; then
  zsh tools/build_macos.sh
fi
exec "$pet_binary" "$PWD/frames3d"

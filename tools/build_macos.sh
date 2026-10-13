#!/bin/zsh
set -eu
cd "${0:A:h:h}"
pet_app="build/IvenPet.app"
mkdir -p "$pet_app/Contents/MacOS" "$pet_app/Contents/Resources/frames3d"
pet_compiler="$(xcrun swiftc --version | sed -n 's/.*Apple Swift version \([0-9]*\.[0-9]*\).*/\1/p')"
pet_sdk="${IVEN_PET_SDK:-$(xcrun --show-sdk-path)}"
pet_sdks=("$pet_sdk" /Library/Developer/CommandLineTools/SDKs/MacOSX<->.<->.sdk(NOn))
for pet_candidate in "${pet_sdks[@]}"; do
  pet_interface="$pet_candidate/usr/lib/swift/Swift.swiftmodule/arm64e-apple-macos.swiftinterface"
  [[ -f "$pet_interface" ]] || continue
  pet_sdk_compiler="$(sed -n '2s/.*Apple Swift version \([0-9]*\.[0-9]*\).*/\1/p' "$pet_interface")"
  [[ -n "$pet_sdk_compiler" ]] || continue
  if (( ${pet_sdk_compiler%%.*}*100+${pet_sdk_compiler#*.} <= ${pet_compiler%%.*}*100+${pet_compiler#*.} )); then
    pet_sdk="$pet_candidate"
    break
  fi
done
print "Swift $pet_compiler, SDK $pet_sdk"
xcrun swiftc -O -sdk "$pet_sdk" -target "$(uname -m)-apple-macosx13.0" \
  -module-cache-path "${TMPDIR:-/private/tmp}/iven-pet-swift-cache" \
  native/macos/IvenPet.swift -o "$pet_app/Contents/MacOS/IvenPet"
cp frames3d/*.png frames3d/animation.json "$pet_app/Contents/Resources/frames3d/"
cat > "$pet_app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>IvenPet</string>
<key>CFBundleIdentifier</key><string>lab.iven.desktop-pet</string>
<key>CFBundleName</key><string>Iven Pet</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0.0</string>
<key>LSUIElement</key><true/>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign --force --sign - "$pet_app"
"$pet_app/Contents/MacOS/IvenPet" --self-test
print "Built $pet_app (standalone AppKit, no Python or Codex required)."

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
pet_arch="${IVEN_PET_ARCH:-$(uname -m)}"
case "$pet_arch" in
  universal) pet_arches=(arm64 x86_64) ;;
  arm64|x86_64) pet_arches=("$pet_arch") ;;
  *) print -u2 "Unsupported architecture: $pet_arch"; exit 1 ;;
esac
pet_binaries=()
for pet_target in $pet_arches; do
  pet_binary="build/IvenPet-$pet_target"
  xcrun swiftc -O -sdk "$pet_sdk" -target "$pet_target-apple-macosx13.0" \
    -module-cache-path "${TMPDIR:-/private/tmp}/iven-pet-swift-cache" \
    native/macos/IvenPet.swift -o "$pet_binary"
  pet_binaries+=("$pet_binary")
done
if (( ${#pet_binaries} > 1 )); then
  lipo -create $pet_binaries -output "$pet_app/Contents/MacOS/IvenPet"
else
  cp "$pet_binaries[1]" "$pet_app/Contents/MacOS/IvenPet"
fi
cp frames3d/*.png frames3d/animation.json "$pet_app/Contents/Resources/frames3d/"
cp animation_behaviors.json "$pet_app/Contents/Resources/"
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
pet_version="$(<VERSION)"
[[ "$pet_version" == <->.<->.<-> ]] || { print -u2 "Invalid VERSION"; exit 1; }
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $pet_version" "$pet_app/Contents/Info.plist"
codesign --force --sign - "$pet_app"
"$pet_app/Contents/MacOS/IvenPet" --self-test
print "Built $pet_app (standalone AppKit, no Python or Codex required)."

#!/usr/bin/env bash
# Recovery for the missing DMG only. Tauri still builds and signs the exact app;
# hdiutil packages it without the failing bundle_dmg.sh presentation wrapper.
set -euo pipefail
test "$RUNNER_OS" = macOS
test "$GITHUB_ACTIONS" = true
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
test "$(git rev-parse HEAD)" = "$SOURCE_SHA"
case "$EDITION" in
  Local) identifier=com.zimo.app ;;
  Cloud) identifier=com.zimo.cloud ;;
  *) exit 1 ;;
esac
app="src-tauri/target/release/bundle/macos/Zimo ${EDITION}.app"
plist="$app/Contents/Info.plist"
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$plist")" = "$identifier"
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$plist")" = "$VERSION"
codesign --verify --deep --strict --verbose=2 "$app"
binary="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$plist")"
lipo -verify_arch arm64 "$app/Contents/MacOS/$binary"
stage="$(mktemp -d "$RUNNER_TEMP/zimo-dmg-XXXXXX")"
ditto "$app" "$stage/Zimo ${EDITION}.app"
ln -s /Applications "$stage/Applications"
mkdir -p release_artifacts
destination="release_artifacts/Zimo-${EDITION}-mac-${VERSION}.dmg"
test ! -e "$destination"
hdiutil create -volname "Zimo ${EDITION}" -srcfolder "$stage" -format UDZO -fs HFS+ "$destination"
hdiutil verify "$destination"
{
  printf 'release_tag=%s\nsource_sha=%s\nworkflow_sha=%s\nrun_id=%s\n' "$RELEASE_TAG" "$SOURCE_SHA" "$GITHUB_SHA" "$GITHUB_RUN_ID"
  shasum -a 256 "$destination"
} > release_artifacts/macos-recovery-provenance.txt

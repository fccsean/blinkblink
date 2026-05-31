#!/bin/bash
#
# Build the Eye Protection app with py2app and re-sign it.
# Re-signing is required because py2app's ad-hoc signatures often fail
# runtime code-signing validation on modern macOS (SIGKILL Code Signature Invalid).
#
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Cleaning previous build ==="
rm -rf build dist

echo "=== Building with py2app ==="
python3 setup.py py2app

APP="dist/Eye Protection.app"

echo "=== Removing quarantine attributes ==="
xattr -cr "$APP" 2>/dev/null || true

echo "=== Removing unused Tk/Tcl frameworks ==="
rm -rf "$APP/Contents/Frameworks/Tk.framework" "$APP/Contents/Frameworks/Tcl.framework"

echo "=== Fixing corrupted libmediapipe.dylib ==="
MEDIAPIPE_DYLIB="$(find /Library/Frameworks/Python.framework/Versions/3.13/lib -name libmediapipe.dylib -print -quit 2>/dev/null)"
TARGET_DYLIB="$APP/Contents/Resources/lib/python3.13/mediapipe/tasks/c/libmediapipe.dylib"
if [ -f "$MEDIAPIPE_DYLIB" ] && [ -f "$TARGET_DYLIB" ]; then
    cp -f "$MEDIAPIPE_DYLIB" "$TARGET_DYLIB"
    echo "  Replaced with fresh copy: $MEDIAPIPE_DYLIB"
else
    echo "  Skipping (source or target not found)"
fi

echo "=== Re-signing all native libraries ==="
find "$APP/Contents" \( -name "*.dylib" -o -name "*.so" \) -print0 | while IFS= read -r -d '' f; do
    codesign --force --sign - --timestamp=none "$f" 2>/dev/null
done

echo "=== Re-signing Python framework ==="
codesign --force --deep --sign - --timestamp=none "$APP/Contents/Frameworks/Python.framework" 2>/dev/null || true

echo "=== Re-signing app bundle ==="
codesign --force --deep --sign - --timestamp=none "$APP" 2>/dev/null || true

echo "=== Done: $APP ==="

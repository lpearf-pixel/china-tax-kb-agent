#!/usr/bin/env bash
set -euo pipefail

TOOLS="$(cd "$(dirname "$0")/.." && pwd)"
RUNNER="$TOOLS/run_weekly_update.sh"
PYTHON_BIN="$(command -v python3)"
PLIST="$HOME/Library/LaunchAgents/com.local.taxkb.weekly-update.plist"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.local.taxkb.weekly-update</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${RUNNER}</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>PYTHON_BIN</key><string>${PYTHON_BIN}</string></dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>1</integer>
    <key>Hour</key><integer>9</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed: $PLIST"
echo "Schedule: every Monday at 09:00 local time"

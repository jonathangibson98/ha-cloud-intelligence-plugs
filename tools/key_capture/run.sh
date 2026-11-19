#!/usr/bin/env bash
# Captures Cloud Intelligence plug keys from your phone's app traffic.
# Needs Docker. Usage: bash run.sh
set -euo pipefail

RAW="https://raw.githubusercontent.com/jonathangibson98/ha-cloud-intelligence-plugs/main/tools/key_capture/capture_keys.py"
DIR="$(cd "$(dirname "$0")" && pwd)"
ADDON="$DIR/capture_keys.py"
PORT="${PORT:-8080}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker isn't installed on this machine." >&2
  exit 1
fi

if [ ! -f "$ADDON" ]; then
  echo "Downloading capture_keys.py..."
  curl -fsSL "$RAW" -o "$ADDON"
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
IP="${IP:-YOUR-COMPUTER-IP}"

cat <<INFO

 On your phone:
   1. Wi-Fi settings -> your network -> Configure Proxy -> Manual
        Server: $IP    Port: $PORT
   2. In Safari open http://mitm.it and install the certificate profile.
        iPhone: Settings -> General -> VPN & Device Management -> install it,
        then Settings -> General -> About -> Certificate Trust Settings -> turn it on.
   3. Open Cloud Intelligence and tap into each plug.

 When you're done: press Ctrl+C here, turn the phone's proxy back OFF,
 and delete the certificate profile from your phone.

INFO

exec docker run --rm -it --name ci-key-capture \
  -p "$PORT:8080" \
  -v "$ADDON:/addon/capture_keys.py:ro" \
  mitmproxy/mitmproxy \
  mitmdump -q -s /addon/capture_keys.py

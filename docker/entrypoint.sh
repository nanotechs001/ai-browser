#!/bin/sh
# Start Chromium for ai-browser. Chromium's DevTools endpoint stays on 127.0.0.1:9222 inside the
# container; a token-guarded proxy exposes it on 9223 so Docker can publish it to the host.
set -e

rm -f /profile/SingletonLock /profile/SingletonSocket /profile/SingletonCookie

python3 /usr/local/bin/aib-cdp-proxy 9223 9222 &

# --no-sandbox: Chromium's own sandbox needs kernel features Docker's default profile
# blocks; the container itself is the isolation boundary (see the engine spec).
exec chromium \
  --headless=new \
  --no-sandbox \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --user-data-dir=/profile \
  --window-size=1440,900 \
  --no-first-run \
  --no-default-browser-check \
  --disable-extensions \
  --disable-background-timer-throttling \
  --disable-renderer-backgrounding \
  --disable-backgrounding-occluded-windows \
  --disable-features=Translate,MediaRouter \
  --disable-smooth-scrolling \
  --mute-audio \
  --password-store=basic \
  about:blank

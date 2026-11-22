#!/bin/sh
# Online version: connect to your tailnet (to reach the AI on your PC), then start Amt-Lotse.
# Space settings needed (see the main README, "Always online"):
#   secrets:   AMT_LOTSE_PASSWORD (at least 10 characters),
#              TS_AUTHKEY: a Tailscale OAuth client secret (tskey-client-..., never expires) or an auth key (tagged)
#   variable:  OLLAMA_HOST = http://<your-pc>.<your-tailnet>.ts.net:11434
TS=/tmp/tailscale
mkdir -p "$TS"
tailscaled --tun=userspace-networking --socks5-server=localhost:1055 \
  --statedir="$TS" --socket="$TS/tailscaled.sock" > "$TS/tailscaled.log" 2>&1 &

if [ -n "$TS_AUTHKEY" ]; then
  # wait until tailscaled is ready (a few seconds at most)
  for i in 1 2 3 4 5 6 7 8 9 10; do [ -S "$TS/tailscaled.sock" ] && break; sleep 1; done
  KEY="$TS_AUTHKEY"
  # an OAuth client secret creates a fresh key at every start; ephemeral: the old Space device disappears by itself
  case "$KEY" in tskey-client-*) KEY="$KEY?ephemeral=true&preauthorized=true" ;; esac
  tailscale --socket="$TS/tailscaled.sock" up --authkey="$KEY" --advertise-tags="${TS_TAGS:-tag:amt-space}" \
    --hostname="${TS_HOSTNAME:-amt-lotse-space}" --timeout=60s || echo "Tailscale could not connect: the page works, but shows that the AI server is off."
else
  echo "TS_AUTHKEY is not set: the page works, but cannot reach the AI on your PC."
fi

export AMT_LOTSE_OLLAMA_PROXY=socks5://localhost:1055
exec amt-lotse-ui --cloud

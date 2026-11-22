"""Online version on a Hugging Face Gradio Space.

Starts Tailscale (to reach the AI on your own PC) in the background, then starts Amt-Lotse.
The page is up at once; it shows "AI server off" until the PC is reachable.

Space settings needed (see the main README, "Always online"):
  secrets:   AMT_LOTSE_PASSWORD (at least 10 characters),
             TS_AUTHKEY: a Tailscale OAuth client secret (tskey-client-..., never expires)
  variable:  OLLAMA_HOST = http://<tailscale-ip-of-your-pc>:11434
"""

import os
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

TAILSCALE_VERSION = os.environ.get("TS_VERSION", "1.104.7")
TS_DIR = Path("/tmp/tailscale")
SOCKET = TS_DIR / "tailscaled.sock"
SOCKS_PORT = 1055

try:   # free Spaces run on ZeroGPU, which refuses to start without one @spaces.GPU function
    import spaces

    @spaces.GPU
    def _unused_gpu() -> None:
        """Never called: the AI runs on your PC, not on this server."""
except ImportError:
    pass


def connect_tailscale() -> None:
    """Download Tailscale, start it without a network device (userspace) and join your tailnet."""
    key = os.environ.get("TS_AUTHKEY", "")
    if not key:
        print("TS_AUTHKEY is not set: the page works, but cannot reach the AI on your PC.", flush=True)
        return
    try:
        TS_DIR.mkdir(parents=True, exist_ok=True)
        folder = f"tailscale_{TAILSCALE_VERSION}_amd64"
        if not (TS_DIR / folder / "tailscaled").exists():
            archive = TS_DIR / "tailscale.tgz"
            urllib.request.urlretrieve(f"https://pkgs.tailscale.com/stable/{folder}.tgz", archive)
            with tarfile.open(archive) as tar:
                try:
                    tar.extractall(TS_DIR, filter="data")
                except TypeError:   # older Python without the filter argument
                    tar.extractall(TS_DIR)
        bin_dir = TS_DIR / folder
        log = open(TS_DIR / "tailscaled.log", "ab")
        subprocess.Popen([str(bin_dir / "tailscaled"), "--tun=userspace-networking",
                          f"--socks5-server=localhost:{SOCKS_PORT}", f"--statedir={TS_DIR}",
                          f"--socket={SOCKET}"], stdout=log, stderr=log)
        for _ in range(15):
            if SOCKET.exists():
                break
            time.sleep(1)
        # an OAuth client secret creates a fresh key at every start; ephemeral: the old Space device disappears by itself
        if key.startswith("tskey-client-"):
            key += "?ephemeral=true&preauthorized=true"
        result = subprocess.run([str(bin_dir / "tailscale"), f"--socket={SOCKET}", "up", f"--authkey={key}",
                                 f"--advertise-tags={os.environ.get('TS_TAGS', 'tag:amt-space')}",
                                 f"--hostname={os.environ.get('TS_HOSTNAME', 'amt-lotse-space')}",
                                 "--timeout=60s"], capture_output=True, text=True)
        print("Tailscale:", "connected" if result.returncode == 0 else f"could not connect: {result.stderr[-300:]}",
              flush=True)
    except Exception as error:   # the page must start anyway
        print(f"Tailscale could not start ({error}): the page works, but shows that the AI server is off.", flush=True)


if __name__ == "__main__":
    os.environ["AMT_LOTSE_OLLAMA_PROXY"] = f"socks5://localhost:{SOCKS_PORT}"
    threading.Thread(target=connect_tailscale, daemon=True).start()

    from amt_lotse.app import main

    sys.argv = ["amt-lotse-ui", "--cloud"]
    main()

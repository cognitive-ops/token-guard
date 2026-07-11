"""Host-side TCP relay: RELAY_BIND:LISTEN -> 127.0.0.1:TARGET.

The SSM port-forwards bind to host loopback only, which docker containers can't
reach via host.docker.internal (the gateway IP). This relay re-exposes them on an
interface the local Grafana container CAN reach.

SECURITY: this carries production Loki (raw user prompts) and Prometheus, with no
auth. Never bind it to 0.0.0.0 — that exposes production data to the whole LAN.
Bind only to a private interface:
  - Docker Desktop (mac/win): 127.0.0.1 works (host.docker.internal routes to host loopback)
  - Linux: the docker bridge gateway (e.g. 172.17.0.1) — container-only, not LAN-routable
The launcher (online-tunnels.sh) sets RELAY_BIND per-platform; default is loopback.
"""

import os
import socket
import threading

BIND = os.environ.get("RELAY_BIND", "127.0.0.1")
if BIND in ("0.0.0.0", "::", ""):
    raise SystemExit(
        f"refusing to bind relay to {BIND!r}: it would expose production Loki/Prometheus "
        "to the LAN. Set RELAY_BIND to 127.0.0.1 (Docker Desktop) or the docker bridge "
        "gateway (Linux, e.g. 172.17.0.1)."
    )

MAPS = [
    (BIND, 3201, "127.0.0.1", 3200),  # online Loki
    (BIND, 3203, "127.0.0.1", 3202),  # online Prometheus
]


def pipe(a, b):
    try:
        while True:
            d = a.recv(65536)
            if not d:
                break
            b.sendall(d)
    except Exception:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass


def serve(lh, lp, th, tp):
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((lh, lp))
    s.listen(128)
    print(f"relay {lh}:{lp} -> {th}:{tp}", flush=True)
    while True:
        c, _ = s.accept()
        try:
            u = socket.create_connection((th, tp), timeout=10)
        except Exception:
            c.close()
            continue
        threading.Thread(target=pipe, args=(c, u), daemon=True).start()
        threading.Thread(target=pipe, args=(u, c), daemon=True).start()


for m in MAPS:
    threading.Thread(target=serve, args=m, daemon=True).start()
print("relay ready", flush=True)
threading.Event().wait()

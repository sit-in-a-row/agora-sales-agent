from __future__ import annotations

import os
import socket
import threading
import webbrowser

import uvicorn


def _is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _select_port() -> int:
    requested = os.getenv("PORT")
    if requested:
        port = int(requested)
        if not _is_free(port):
            raise SystemExit(f"PORT {port} is already in use. Stop the previous server or choose another PORT.")
        return port
    for port in range(8000, 8011):
        if _is_free(port):
            if port != 8000:
                print(f"[Agora] Port 8000 is already in use. Starting v1.6 on http://127.0.0.1:{port} instead.")
                print("[Agora] This avoids accidentally opening an older Agora server still running on port 8000.")
            return port
    raise SystemExit("No free port found in 8000-8010.")


if __name__ == "__main__":
    port = _select_port()
    url = f"http://127.0.0.1:{port}"
    print(f"[Agora] Starting Agora Sales Agent v1.6 at {url}")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False)

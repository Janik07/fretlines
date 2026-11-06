"""`python -m fretlines_api` — запуск приложения целиком: API, разборы и интерфейс."""

import argparse
import socket
import threading
import webbrowser

import uvicorn

from fretlines_api.settings import load_settings


def _free_port(host: str, preferred: int) -> int:
    """Если порт занят (например, другой программой), берём следующий свободный."""
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    return preferred


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="fretlines", description="Fretlines — гитарный аранжировщик"
    )
    parser.add_argument("--host", help="адрес (0.0.0.0 — открыть для локальной сети)")
    parser.add_argument("--port", type=int, help="порт, по умолчанию 8080")
    parser.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    args = parser.parse_args()

    settings = load_settings()
    host = args.host or settings.host
    port = _free_port(host, args.port or settings.port)
    local = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{local}:{port}"
    print(f"\n  Fretlines работает: {url}\n  Остановить — Ctrl+C в этом окне.\n", flush=True)
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run("fretlines_api.main:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()

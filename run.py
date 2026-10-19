"""Start the dashboard: python run.py  (opens http://localhost:8080)"""
import os
import threading
import webbrowser

import uvicorn

PORT = int(os.getenv("PORT", "8080"))
# Hosted platforms (Render, Koyeb, Railway...) dial in over the network, so
# bind every interface there; locally the loopback default stays.
HOST = os.getenv("HOST", "0.0.0.0" if os.getenv("RENDER") or os.getenv("DYNO") else "127.0.0.1")

if __name__ == "__main__" and HOST == "127.0.0.1":
    threading.Timer(2.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
uvicorn.run("app.main:app", host=HOST, port=PORT)   # one process: API + worker + UI

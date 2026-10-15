"""Start the dashboard: python run.py  (opens http://localhost:8080)"""
import os
import threading
import webbrowser

import uvicorn

PORT = int(os.getenv("PORT", "8080"))

if __name__ == "__main__":
    threading.Timer(2.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT)   # one process: API + worker + UI

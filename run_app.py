"""Runner script that boots both the FastAPI backend and React Vite frontend."""

import os
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")

# Locate node binary
NODE_EXE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
VITE_BIN = os.path.join(FRONTEND_DIR, "node_modules", "vite", "bin", "vite.js")


def main():
    print("=" * 60, flush=True)
    print("Starting ARIA AI Voice Assistant...", flush=True)
    print("=" * 60, flush=True)

    # 1. Start Backend
    print("[1/2] Starting FastAPI backend on http://127.0.0.1:8000...", flush=True)
    backend_env = os.environ.copy()
    backend_env["PYTHONUNBUFFERED"] = "1"
    backend_proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=BACKEND_DIR,
        env=backend_env,
    )

    # Wait for backend to be ready
    print("Waiting for backend services (Whisper, Groq, gTTS) to initialize...", flush=True)
    for _ in range(60):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as resp:
                if resp.status == 200:
                    print("Backend is ready and healthy!", flush=True)
                    break
        except Exception:
            time.sleep(0.5)
    else:
        print("Warning: Backend health check took longer than expected.", flush=True)

    # 2. Start Frontend
    print("\n[2/2] Starting Vite frontend on http://127.0.0.1:5173...", flush=True)
    frontend_env = os.environ.copy()
    nodejs_dir = os.path.dirname(NODE_EXE) if os.path.isabs(NODE_EXE) else ""
    if nodejs_dir and nodejs_dir not in frontend_env.get("PATH", ""):
        frontend_env["PATH"] = nodejs_dir + os.pathsep + frontend_env.get("PATH", "")

    frontend_proc = subprocess.Popen(
        [NODE_EXE, VITE_BIN, "--host", "0.0.0.0", "--port", "5173"],
        cwd=FRONTEND_DIR,
        env=frontend_env,
    )

    time.sleep(2)

    print("\n" + "=" * 60, flush=True)
    print("🚀 TS AI Voice Assistant is running successfully!", flush=True)
    print("   👉 Open in your browser: http://localhost:5173", flush=True)
    print("   👉 Backend API docs:     http://localhost:8000/docs", flush=True)
    print("=" * 60, flush=True)
    print("Press Ctrl+C to stop both servers.\n")

    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None:
                print("Backend exited unexpectedly.")
                break
            if frontend_proc.poll() is not None:
                print("Frontend exited unexpectedly.")
                break
    except KeyboardInterrupt:
        print("\nStopping servers...")
    finally:
        backend_proc.terminate()
        frontend_proc.terminate()
        backend_proc.wait()
        frontend_proc.wait()
        print("Servers stopped cleanly.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Startup script for the Veridia FastAPI backend
"""

import os
import sys
import io
import uvicorn
from app.paths import DASHBOARD_DIR, ENV_FILE, UPLOAD_DIR, ensure_runtime_dirs, load_project_env

# Force UTF-8 output on Windows so emoji don't crash
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import fastapi
        import uvicorn
        import pandas
        import numpy
        import groq
        import dotenv
        print("[OK] All dependencies are installed")
    except ImportError as e:
        print(f"[ERROR] Missing dependency: {e}")
        print("Please run: pip install -r requirements.txt")
        return False
    return True

def check_environment():
    """Check if environment variables are set"""
    load_project_env()

    if not os.getenv("GROQ_API_KEY"):
        print("[WARN] GROQ_API_KEY not detected in environment or .env.local")
        print("[INFO] To enable dashboard generation, add GROQ_API_KEY to backend/.env.local")
        print("[INFO] Example: GROQ_API_KEY=gsk_...")
    else:
        print("[OK] Environment variables configured (GROQ_API_KEY detected)")
    return True

def create_directories():
    """Create necessary directories"""
    ensure_runtime_dirs()
    for directory in (UPLOAD_DIR, DASHBOARD_DIR):
        print(f"[OK] Ensured directory exists: {directory}")

def main():
    """Main startup function"""
    print("=== Starting Veridia Backend ===")
    print("=" * 50)

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Check environment
    if not check_environment():
        sys.exit(1)

    # Create directories
    create_directories()

    port = int(os.environ.get("BACKEND_PORT", "8000"))
    print(f"\n[INFO] Backend ready to start!")
    print(f"[INFO] API will be available at: http://localhost:{port}")
    print(f"[INFO] API documentation at:     http://localhost:{port}/docs")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 50)

    try:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=port,
            reload=True,
            log_level="info",
        )
    except KeyboardInterrupt:
        print("\n\n[INFO] Server stopped by user")
    except Exception as e:
        print(f"\n[ERROR] Server failed to start: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
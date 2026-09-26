import ast
import io
import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx
import uvicorn
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from app.paths import (
    CHROMA_DIR,
    DASHBOARD_DIR,
    DATA_DIR,
    REPO_ROOT,
    UPLOAD_DIR,
    ensure_runtime_dirs,
    load_project_env,
)
from app.services.prompt_chain_new import (
    _validate_code,
    _validate_dash_code,
    apply_user_edit_minimal,
    create_dashboard,
    fix_generated_code,
    sanitize_and_modernize_dash_code,
)

# Load environment before accessing any variables
load_project_env()

# Ensuring runtime directories exist
ensure_runtime_dirs()
DASHBOARD_ROOT = DASHBOARD_DIR

app = FastAPI(title="Veridia Backend", version="1.0.0")

# CORS middleware for frontend communication (supports localhost and network IP access)
cors_origins_env = os.getenv("CORS_ORIGINS", "*")
if cors_origins_env and cors_origins_env.strip() != "*":
    origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_origin_regex=r"https?://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# In-memory registry for running dashboards
running_dashboards: Dict[str, dict] = {}

# Map Dash ports to stable paths that reverse proxies (e.g. Nginx) can mount
PORT_PATH_MAP = {
    8050: "/dash1/",
    8051: "/dash2/",
    8052: "/dash3/",
    8053: "/dash4/",
    8054: "/dash5/",
    8055: "/dash6/",
    8056: "/dash7/",
    8057: "/dash8/",
    8058: "/dash9/",
    8059: "/dash10/",
    8060: "/dash11/",
}


def _validate_dashboard_id(dashboard_id: str) -> None:
    """Validate dashboard ID to prevent path traversal attacks."""
    if not dashboard_id or not re.match(r"^[a-zA-Z0-9_\-]+$", dashboard_id):
        raise HTTPException(status_code=400, detail="Invalid dashboard ID")


def _kill_process_group(pid: Optional[int]) -> None:
    """Safely terminate a subprocess and its children across Windows and POSIX."""
    if not pid:
        return
    if sys.platform == "win32":
        try:
            # On Windows, taskkill /F /T kills the process tree cleanly
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    else:
        if hasattr(os, "killpg"):
            try:
                os.killpg(pid, signal.SIGTERM)
                time.sleep(0.3)
            except ProcessLookupError:
                pass
            except Exception:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except Exception:
                    pass
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception:
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass


def _get_process_creation_kwargs() -> dict:
    """Return platform-specific kwargs for subprocess creation."""
    kwargs = {}
    if hasattr(os, "setsid"):
        kwargs["preexec_fn"] = os.setsid
    elif sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return kwargs


def _status_file_for(dashboard_dir: Path) -> Path:
    return dashboard_dir / "status.json"


def _save_status(dashboard_id: str) -> None:
    try:
        info = running_dashboards.get(dashboard_id)
        if not info:
            return
        dashboard_dir = Path(info.get("dashboard_dir", ""))
        if not dashboard_dir or not dashboard_dir.exists():
            return
        with open(_status_file_for(dashboard_dir), "w", encoding="utf-8") as f:
            # Serialize only JSON-safe fields (skip non-serializable objects)
            safe_info = {
                k: v for k, v in info.items() if isinstance(v, (str, int, float, bool, list, dict, type(None)))
            }
            json.dump(safe_info, f, indent=2)
    except Exception as e:
        logging.warning(f"Failed to save status for {dashboard_id}: {e}")


def _restore_status_from_disk(dashboard_id: str) -> Optional[dict]:
    """Attempt to restore dashboard metadata from disk if not present in memory."""
    dashboard_dir = DASHBOARD_ROOT / dashboard_id
    status_file = _status_file_for(dashboard_dir)
    if status_file.exists():
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                info = json.load(f)
            running_dashboards[dashboard_id] = info
            return info
        except Exception:
            pass
    if dashboard_dir.exists():
        code_file = dashboard_dir / "dashboard_app.py"
        minimal = {
            "status": "completed" if code_file.exists() else "unknown",
            "dashboard_dir": str(dashboard_dir),
            "output_file": str(code_file) if code_file.exists() else None,
            "running": False,
            "port": None,
        }
        running_dashboards[dashboard_id] = minimal
        return minimal
    return None


def get_dashboard_url_and_base_path(dashboard_id: str, port: int, request: Request) -> Tuple[str, str]:
    """Determine the external reverse-proxy dashboard URL and base path.
    
    Routes dashboard requests through FastAPI backend proxy (/dashproxy/{dashboard_id}/)
    so dashboards are accessible over LAN Network URLs and Vercel/Render production deployments.
    """
    base_path = f"/dashproxy/{dashboard_id}/"
    external_dash_base = os.getenv("EXTERNAL_DASHBOARD_BASE_URL", "").strip()

    if external_dash_base:
        external_url = f"{external_dash_base.rstrip('/')}{base_path}"
    else:
        x_forwarded_proto = request.headers.get("x-forwarded-proto") or request.headers.get("X-Forwarded-Proto")
        x_forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("X-Forwarded-Host")

        if x_forwarded_host:
            scheme = x_forwarded_proto or request.url.scheme or "http"
            host_name = x_forwarded_host
            external_url = f"{scheme}://{host_name}{base_path}"
        else:
            host = request.headers.get("host") or f"{request.url.hostname}:{request.url.port}"
            scheme = request.url.scheme or "http"
            external_url = f"{scheme}://{host}{base_path}"

    return external_url, base_path


@app.api_route(
    "/dashproxy/{dashboard_id}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
)
@app.api_route(
    "/dashproxy/{dashboard_id}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
)
async def proxy_dashboard(dashboard_id: str, request: Request, path: str = ""):
    """Proxy HTTP requests to internal Dash subprocess ports over unified FastAPI backend port."""
    _validate_dashboard_id(dashboard_id)
    info = running_dashboards.get(dashboard_id) or _restore_status_from_disk(dashboard_id)
    if not info or not info.get("port"):
        raise HTTPException(status_code=404, detail="Dashboard process not found or not running")

    port = info["port"]
    target_url = f"http://127.0.0.1:{port}/dashproxy/{dashboard_id}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            req_body = await request.body()
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=req_body,
                follow_redirects=True,
            )

            response_headers = {
                k: v for k, v in resp.headers.items()
                if k.lower() not in ("content-encoding", "transfer-encoding", "content-length")
            }
            response_headers["Access-Control-Allow-Origin"] = "*"
            response_headers["Access-Control-Allow-Methods"] = "*"
            response_headers["Access-Control-Allow-Headers"] = "*"

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=response_headers,
                media_type=resp.headers.get("content-type"),
            )
    except Exception as err:
        logging.error(f"Proxy error for dashboard {dashboard_id} on port {port}: {err}")
        raise HTTPException(status_code=502, detail=f"Error proxying dashboard request: {err}")


def find_available_port(start_port: int = 8050, end_port: int = 8060) -> int:
    """Find an available port in the designated Dash range, avoiding active ports."""
    active_ports = {
        info.get("port")
        for info in running_dashboards.values()
        if info.get("running") and info.get("port")
    }

    for port in range(start_port, end_port + 1):
        if port in active_ports:
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", port))
                return port
        except OSError:
            continue

    # Secondary check without in-memory exclusion
    for port in range(start_port, end_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", port))
                return port
        except OSError:
            continue

    raise RuntimeError(f"No available ports found in range {start_port}-{end_port}")


def _stop_dashboard_process(dashboard_id: str) -> None:
    """Stop any active subprocess for the given dashboard ID."""
    info = running_dashboards.get(dashboard_id)
    if not info:
        return
    pid = info.get("process")
    if pid:
        _kill_process_group(pid)
    info["running"] = False
    info["process"] = None
    info["port"] = None
    _save_status(dashboard_id)


def _ensure_cors_in_dash_code(code: str) -> str:
    """Ensure generated Dash code includes CORS headers so iframe embedding over LAN/IP works cleanly."""
    if "Access-Control-Allow-Origin" in code or "after_request" in code:
        return code

    cors_snippet = (
        "\n# Enable CORS headers for iframe embedding\n"
        "if 'app' in globals() and hasattr(app, 'server'):\n"
        "    @app.server.after_request\n"
        "    def _add_cors_headers(response):\n"
        "        response.headers['Access-Control-Allow-Origin'] = '*'\n"
        "        response.headers['Access-Control-Allow-Headers'] = '*'\n"
        "        response.headers['Access-Control-Allow-Methods'] = '*'\n"
        "        return response\n\n"
    )

    if 'if __name__ == "__main__":' in code:
        return code.replace('if __name__ == "__main__":', cors_snippet + 'if __name__ == "__main__":')
    elif "if __name__ == '__main__':" in code:
        return code.replace("if __name__ == '__main__':", cors_snippet + "if __name__ == '__main__':")

    return code + cors_snippet


def _ensure_host_binding(code: str) -> str:
    """Ensure the generated Dash app's app.run() call binds to 0.0.0.0.

    The FastAPI reverse proxy reaches the Dash subprocess via 127.0.0.1:{port}.
    If the subprocess only listens on localhost the proxy still works, but if
    the user hasn't set host= at all, or set it to '127.0.0.1', we normalise
    it to '0.0.0.0' so the subprocess is reachable both from the proxy and
    from direct LAN access.
    """
    # Replace host='localhost' or host='127.0.0.1' with host='0.0.0.0'
    code = re.sub(r"""host\s*=\s*['"](?:localhost|127\.0\.0\.1)['"]""", "host='0.0.0.0'", code)

    # If there's an app.run / app.run_server call without a host keyword, inject one.
    # Match patterns like: app.run(  or app.run_server(  (possibly with existing args)
    def _add_host_kwarg(m: re.Match) -> str:
        call_text = m.group(0)
        if "host=" in call_text:
            return call_text
        # Insert host='0.0.0.0' as the first keyword argument
        # Find the closing paren and insert before it
        open_paren = call_text.index("(")
        inner = call_text[open_paren + 1 :].rstrip()
        if inner.endswith(")"):
            inner = inner[:-1].rstrip()
            sep = ", " if inner.strip() else ""
            return call_text[: open_paren + 1] + inner + sep + "host='0.0.0.0')"
        return call_text

    code = re.sub(r"app\.run(?:_server)?\s*\([^)]*\)", _add_host_kwarg, code)
    return code


def _start_dashboard_subprocess(
    dashboard_id: str,
    dashboard_dir: Path,
    code_path: Path,
    port: int,
    base_path: Optional[str] = None,
) -> Tuple[bool, str, Optional[int]]:
    """Start the Dash application subprocess, verify startup, and stream logs.
    
    Returns (is_running, error_text, pid)
    """
    _stop_dashboard_process(dashboard_id)

    # Patch the script before launching: ensure DBC modernization, CORS headers, and 0.0.0.0 host binding
    try:
        if code_path.exists():
            code_text = code_path.read_text(encoding="utf-8")
            patched = sanitize_and_modernize_dash_code(code_text)
            patched = _ensure_cors_in_dash_code(patched)
            patched = _ensure_host_binding(patched)
            if patched != code_text:
                code_path.write_text(patched, encoding="utf-8")
    except Exception as e:
        logging.warning(f"Failed to patch {code_path}: {e}")

    script_name = code_path.name
    cmd = [sys.executable, script_name]

    child_env = {**os.environ, "PORT": str(port), "PYTHONUNBUFFERED": "1"}
    if base_path and base_path != "/":
        child_env["BASE_PATH"] = base_path

    stdout_log = open(dashboard_dir / "app_stdout.log", "ab")
    stderr_log = open(dashboard_dir / "app_stderr.log", "ab")

    process = subprocess.Popen(
        cmd,
        cwd=dashboard_dir,
        env=child_env,
        stdout=stdout_log,
        stderr=stderr_log,
        **_get_process_creation_kwargs(),
    )

    # Poll for port readiness instead of a fixed sleep — Dash can take several
    # seconds to import dependencies, especially on the first run.
    deadline = time.monotonic() + 15.0
    port_ready = False
    while time.monotonic() < deadline:
        # Abort early if the process already crashed
        if process.poll() is not None:
            break
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                port_ready = True
                break
        except OSError:
            time.sleep(0.5)

    if process.poll() is not None:
        try:
            stdout_log.close()
            stderr_log.close()
        except Exception:
            pass
        err_text = ""
        try:
            err_text = (dashboard_dir / "app_stderr.log").read_text(encoding="utf-8", errors="ignore")
            # Persist error text to run_error.log for auto-fix diagnostics
            (dashboard_dir / "run_error.log").write_text(err_text, encoding="utf-8")
        except Exception:
            pass
        return False, err_text or "Process exited immediately during startup", None

    if not port_ready:
        logging.warning(f"Dashboard {dashboard_id} port {port} not ready within 15s but process alive — continuing")

    return True, "", process.pid


# Pipeline stage descriptions for client tracking
pipeline_stages = {
    "stage_1": "Analyzing your dataset comprehensively",
    "stage_2": "Searching for similar visualization examples",
    "stage_3": "Designing your dashboard layout",
    "stage_4": "Generating interactive visualization code",
    "stage_5": "Optimizing code for best performance",
    "stage_6": "Testing and correcting any errors",
}


@app.get("/")
async def root():
    return {"message": "Veridia Backend API", "status": "running"}


@app.get("/health")
async def health():
    groq_configured = bool(os.getenv("GROQ_API_KEY"))
    return {
        "status": "healthy",
        "groq_configured": groq_configured,
        "groq_status": "configured" if groq_configured else "missing",
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "upload_dir_exists": UPLOAD_DIR.exists(),
        "dashboard_dir_exists": DASHBOARD_ROOT.exists(),
        "models": {
            "analysis": os.getenv("GROQ_MODEL_ANALYSIS", "openai/gpt-oss-120b"),
            "design": os.getenv("GROQ_MODEL_DESIGN", "openai/gpt-oss-120b"),
            "code": os.getenv("GROQ_MODEL_CODE", "openai/gpt-oss-120b"),
            "optimize": os.getenv("GROQ_MODEL_OPTIMIZE", "openai/gpt-oss-120b"),
        },
    }


@app.get("/data/{filename}")
async def download_dataset(filename: str):
    """Serve sample datasets from data folders safely."""
    try:
        # Prevent path traversal
        clean_name = os.path.basename(filename)
        candidates = [
            DATA_DIR.resolve(),
            (REPO_ROOT / "data").resolve(),
        ]

        found_path = None
        for data_dir in candidates:
            candidate = (data_dir / clean_name).resolve()
            if data_dir in candidate.parents and candidate.exists() and candidate.is_file():
                found_path = candidate
                break

        if not found_path:
            raise HTTPException(status_code=404, detail="Dataset not found")

        return FileResponse(str(found_path), media_type="text/csv", filename=clean_name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to serve dataset: {e}")


@app.post("/upload-dataset")
async def upload_dataset(file: UploadFile = File(...)):
    """Upload a dataset file (CSV)."""
    try:
        if not file.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only CSV files are supported")

        file_id = str(uuid.uuid4())
        file_path = UPLOAD_DIR / f"{file_id}.csv"

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "file_id": file_id,
            "filename": file.filename,
            "file_path": str(file_path),
            "message": "Dataset uploaded successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.post("/generate-dashboard")
async def generate_dashboard(
    background_tasks: BackgroundTasks,
    file_id: str = Form(...),
    user_prompt: str = Form(...),
):
    """Generate dashboard using the prompt chain."""
    try:
        _validate_dashboard_id(file_id)

        if not os.getenv("GROQ_API_KEY"):
            raise HTTPException(
                status_code=400,
                detail="GROQ_API_KEY is not configured. Please set GROQ_API_KEY in backend/.env.local or your environment variables.",
            )

        file_path = UPLOAD_DIR / f"{file_id}.csv"
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Dataset not found for file_id {file_id}")

        dashboard_id = str(uuid.uuid4())
        dashboard_dir = DASHBOARD_ROOT / dashboard_id
        dashboard_dir.mkdir(parents=True, exist_ok=True)

        running_dashboards[dashboard_id] = {
            "status": "generating",
            "current_stage": "stage_1",
            "stage_progress": 0,
            "output_file": None,
            "dashboard_dir": str(dashboard_dir),
            "running": False,
            "port": None,
        }
        _save_status(dashboard_id)

        dataset_path = dashboard_dir / "dataset.csv"
        shutil.copy2(file_path, dataset_path)

        background_tasks.add_task(
            run_dashboard_generation,
            dataset_path,
            user_prompt,
            dashboard_dir,
            dashboard_id,
        )

        return {
            "dashboard_id": dashboard_id,
            "status": "generating",
            "message": "Dashboard generation started",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {type(e).__name__}: {str(e)}")


def run_dashboard_generation(
    dataset_path: Path,
    user_prompt: str,
    dashboard_dir: Path,
    dashboard_id: str,
):
    """Run the multi-stage dashboard generation pipeline."""
    try:
        def _on_progress(stage: str, progress: int, note: Optional[str] = None):
            try:
                if dashboard_id in running_dashboards:
                    running_dashboards[dashboard_id]["current_stage"] = stage
                    running_dashboards[dashboard_id]["stage_progress"] = progress
                    if note is not None:
                        running_dashboards[dashboard_id]["stage_note"] = note
                    _save_status(dashboard_id)
            except Exception:
                pass

        _on_progress("stage_1", 16, "Starting comprehensive analysis of your dataset…")

        output_file = create_dashboard(
            str(dataset_path),
            user_prompt,
            str(dashboard_dir),
            dashboard_id,
            progress_cb=_on_progress,
        )

        if not output_file or not os.path.exists(output_file):
            raise FileNotFoundError(f"Generated output file does not exist: {output_file}")

        running_dashboards[dashboard_id].update({
            "status": "completed",
            "output_file": str(output_file),
            "current_stage": "stage_6",
            "stage_progress": 100,
        })
        _save_status(dashboard_id)

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        running_dashboards[dashboard_id] = {
            "status": "failed",
            "error": f"{type(e).__name__}: {str(e)}",
            "error_trace": error_trace,
            "current_stage": "failed",
            "stage_progress": 0,
            "dashboard_dir": str(dashboard_dir),
            "running": False,
            "port": None,
        }
        _save_status(dashboard_id)


@app.get("/dashboard-status/{dashboard_id}")
async def get_dashboard_status(dashboard_id: str):
    """Get the current status of dashboard generation and execution."""
    _validate_dashboard_id(dashboard_id)

    if dashboard_id not in running_dashboards:
        info = _restore_status_from_disk(dashboard_id)
        if not info:
            raise HTTPException(status_code=404, detail="Dashboard not found")

    return running_dashboards[dashboard_id]


@app.post("/run-dashboard/{dashboard_id}")
async def run_dashboard(dashboard_id: str, request: Request):
    """Start the Dash application subprocess for a completed dashboard."""
    _validate_dashboard_id(dashboard_id)

    if dashboard_id not in running_dashboards:
        _restore_status_from_disk(dashboard_id)

    if dashboard_id not in running_dashboards:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    dashboard_info = running_dashboards[dashboard_id]
    if dashboard_info.get("status") not in ("completed", "running"):
        raise HTTPException(status_code=400, detail="Dashboard is not ready to run")

    dashboard_dir = Path(dashboard_info["dashboard_dir"])
    output_file = dashboard_info.get("output_file")

    code_path = None
    if output_file and os.path.exists(output_file):
        code_path = Path(output_file)
    else:
        candidate = dashboard_dir / "dashboard_app.py"
        if candidate.exists():
            code_path = candidate
        else:
            raise HTTPException(status_code=404, detail="Dashboard code file not found")

    port = find_available_port(8050, 8060)
    external_url, base_path = get_dashboard_url_and_base_path(dashboard_id, port, request)

    is_running, err_msg, pid = _start_dashboard_subprocess(
        dashboard_id=dashboard_id,
        dashboard_dir=dashboard_dir,
        code_path=code_path,
        port=port,
        base_path=base_path,
    )

    if not is_running:
        # Attempt automatic recovery before returning failure
        try:
            logging.info(f"Dashboard {dashboard_id} initial run failed: {err_msg}. Attempting immediate auto-fix.")
            error_text = err_msg or ""
            if (dashboard_dir / "run_error.log").exists():
                error_text = (dashboard_dir / "run_error.log").read_text(encoding="utf-8", errors="ignore") or error_text
            fixed_code = fix_generated_code(str(code_path), error_text, str(dashboard_dir))
            if fixed_code:
                code_path.write_text(fixed_code, encoding="utf-8")
                is_running, err_msg, pid = _start_dashboard_subprocess(
                    dashboard_id=dashboard_id,
                    dashboard_dir=dashboard_dir,
                    code_path=code_path,
                    port=port,
                    base_path=base_path,
                )
        except Exception as rec_err:
            logging.warning(f"Recovery attempt encountered exception: {rec_err}")

    if is_running:
        dashboard_info.update({
            "running": True,
            "port": port,
            "process": pid,
            "output_file": str(code_path),
            "url": external_url,
            "base_path": base_path,
            "status": "running",
            "needs_fix": False,
            "error": None,
        })
        _save_status(dashboard_id)

        return {
            "dashboard_id": dashboard_id,
            "status": "running",
            "url": external_url,
            "port": port,
        }
    else:
        dashboard_info.update({
            "running": False,
            "port": None,
            "process": None,
            "status": "failed",
            "error": err_msg,
            "needs_fix": True,
        })
        _save_status(dashboard_id)

        raise HTTPException(
            status_code=500,
            detail=f"Failed to start dashboard: {err_msg}. Call /fix-dashboard/{dashboard_id} to attempt auto-fix.",
        )


@app.post("/fix-dashboard/{dashboard_id}")
async def fix_dashboard(dashboard_id: str, request: Request):
    """Automatically fix runtime errors in generated Dash code and restart the dashboard."""
    _validate_dashboard_id(dashboard_id)

    if dashboard_id not in running_dashboards:
        _restore_status_from_disk(dashboard_id)

    if dashboard_id not in running_dashboards:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    dashboard_info = running_dashboards[dashboard_id]
    dashboard_dir = Path(dashboard_info.get("dashboard_dir", ""))
    output_file = dashboard_info.get("output_file")
    if not output_file or not os.path.exists(output_file):
        output_file = str(dashboard_dir / "dashboard_app.py")

    if not os.path.exists(output_file):
        raise HTTPException(status_code=400, detail="No dashboard code file available to fix")

    # Read the captured error log
    error_text = ""
    error_log_path = dashboard_dir / "run_error.log"
    if error_log_path.exists():
        try:
            error_text = error_log_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    if not error_text and (dashboard_dir / "app_stderr.log").exists():
        try:
            error_text = (dashboard_dir / "app_stderr.log").read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    if not error_text:
        error_text = dashboard_info.get("error", "Unknown startup error")

    fixed_code = fix_generated_code(output_file, error_text, str(dashboard_dir))
    if not fixed_code:
        raise HTTPException(
            status_code=500,
            detail="Auto-fix failed to produce a valid correction. See run_error.log for details.",
        )

    # Sanitize and validate the fixed code before saving
    fixed_code = sanitize_and_modernize_dash_code(fixed_code)
    is_valid, issues = _validate_dash_code(fixed_code)
    if not is_valid:
        # Minimal syntax validation fallback
        is_syn_valid, syn_err = _validate_code(fixed_code)
        if not is_syn_valid:
            raise HTTPException(status_code=500, detail=f"Fixed code failed validation: {syn_err}")

    # Overwrite the code file
    code_path = Path(output_file)
    try:
        code_path.write_text(fixed_code, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write fixed code: {e}")

    # Launch fixed application
    port = find_available_port(8050, 8060)
    external_url, base_path = get_dashboard_url_and_base_path(dashboard_id, port, request)

    is_running, err_msg, pid = _start_dashboard_subprocess(
        dashboard_id=dashboard_id,
        dashboard_dir=dashboard_dir,
        code_path=code_path,
        port=port,
        base_path=base_path,
    )

    if is_running:
        dashboard_info.update({
            "running": True,
            "port": port,
            "process": pid,
            "output_file": str(code_path),
            "url": external_url,
            "base_path": base_path,
            "status": "running",
            "needs_fix": False,
            "error": None,
        })
        _save_status(dashboard_id)

        return {
            "dashboard_id": dashboard_id,
            "status": "running",
            "url": external_url,
            "port": port,
        }
    else:
        dashboard_info.update({
            "running": False,
            "port": None,
            "process": None,
            "status": "failed",
            "error": err_msg,
            "needs_fix": True,
        })
        _save_status(dashboard_id)

        raise HTTPException(
            status_code=500,
            detail=f"Failed to start dashboard after fix: {err_msg}",
        )


@app.post("/chat-edit/{dashboard_id}")
async def chat_edit_dashboard(dashboard_id: str, request: Request):
    """Apply an AI-powered minimal modification to the existing dashboard code and reload."""
    _validate_dashboard_id(dashboard_id)

    if dashboard_id not in running_dashboards:
        _restore_status_from_disk(dashboard_id)

    if dashboard_id not in running_dashboards:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    payload = await request.json()
    user_message = (payload or {}).get("message")
    if not isinstance(user_message, str) or not user_message.strip():
        raise HTTPException(status_code=400, detail="'message' is required in request body")

    info = running_dashboards[dashboard_id]
    dashboard_dir = Path(info.get("dashboard_dir", ""))
    if not dashboard_dir.exists():
        raise HTTPException(status_code=404, detail="Dashboard directory not found")

    output_file = info.get("output_file")
    if output_file and os.path.exists(output_file):
        code_path = Path(output_file)
    else:
        code_path = dashboard_dir / "dashboard_app.py"

    if not code_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard code file not found")

    existing_code = code_path.read_text(encoding="utf-8")

    # Load context if available
    analysis_result = {}
    dataset_summary = {}
    try:
        analysis_path = dashboard_dir / "analysis_result.json"
        if analysis_path.exists():
            analysis_result = json.loads(analysis_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    try:
        dataset_summary_path = dashboard_dir / "dataset_summary.json"
        if dataset_summary_path.exists():
            dataset_summary = json.loads(dataset_summary_path.read_text(encoding="utf-8"))
    except Exception:
        pass

    updated_code = apply_user_edit_minimal(
        existing_code=existing_code,
        user_request=user_message,
        dataset_summary=dataset_summary,
        analysis_result=analysis_result,
    )

    is_valid, err = _validate_code(updated_code)
    if not is_valid:
        raise HTTPException(status_code=500, detail=f"Model returned invalid code: {err}")

    code_path.write_text(updated_code, encoding="utf-8")

    port = find_available_port(8050, 8060)
    external_url, base_path = get_dashboard_url_and_base_path(dashboard_id, port, request)

    is_running, err_msg, pid = _start_dashboard_subprocess(
        dashboard_id=dashboard_id,
        dashboard_dir=dashboard_dir,
        code_path=code_path,
        port=port,
        base_path=base_path,
    )

    if is_running:
        info.update({
            "running": True,
            "port": port,
            "process": pid,
            "output_file": str(code_path),
            "url": external_url,
            "base_path": base_path,
            "status": "running",
            "needs_fix": False,
            "error": None,
        })
        _save_status(dashboard_id)

        return {
            "dashboard_id": dashboard_id,
            "status": "running",
            "url": external_url,
            "port": port,
            "code": updated_code,
        }
    else:
        info.update({
            "running": False,
            "port": None,
            "process": None,
            "status": "failed",
            "error": err_msg,
            "needs_fix": True,
        })
        _save_status(dashboard_id)

        raise HTTPException(status_code=500, detail=f"Failed to start dashboard after chat edit: {err_msg}")


@app.post("/update-code/{dashboard_id}")
async def update_code_and_run(dashboard_id: str, request: Request):
    """Write user-edited code to the dashboard file and reload."""
    _validate_dashboard_id(dashboard_id)

    if dashboard_id not in running_dashboards:
        _restore_status_from_disk(dashboard_id)

    if dashboard_id not in running_dashboards:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    payload = await request.json()
    code = (payload or {}).get("code")
    if not isinstance(code, str) or not code.strip():
        raise HTTPException(status_code=400, detail="'code' is required in request body")

    # Validate Python syntax
    is_valid, err = _validate_code(code)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Python syntax error: {err}")

    info = running_dashboards[dashboard_id]
    dashboard_dir = Path(info.get("dashboard_dir", ""))
    if not dashboard_dir.exists():
        raise HTTPException(status_code=404, detail="Dashboard directory not found")

    output_file = info.get("output_file")
    code_path = Path(output_file) if output_file and os.path.exists(output_file) else dashboard_dir / "dashboard_app.py"

    code_path.write_text(code, encoding="utf-8")

    port = find_available_port(8050, 8060)
    external_url, base_path = get_dashboard_url_and_base_path(dashboard_id, port, request)

    is_running, err_msg, pid = _start_dashboard_subprocess(
        dashboard_id=dashboard_id,
        dashboard_dir=dashboard_dir,
        code_path=code_path,
        port=port,
        base_path=base_path,
    )

    if is_running:
        info.update({
            "running": True,
            "port": port,
            "process": pid,
            "output_file": str(code_path),
            "url": external_url,
            "base_path": base_path,
            "status": "running",
            "needs_fix": False,
            "error": None,
        })
        _save_status(dashboard_id)

        return {
            "dashboard_id": dashboard_id,
            "status": "running",
            "url": external_url,
            "port": port,
            "code": code,
        }
    else:
        info.update({
            "running": False,
            "port": None,
            "process": None,
            "status": "failed",
            "error": err_msg,
            "needs_fix": True,
        })
        _save_status(dashboard_id)

        raise HTTPException(status_code=500, detail=f"Failed to start dashboard after update: {err_msg}")


@app.get("/stop-dashboard/{dashboard_id}")
async def stop_dashboard(dashboard_id: str):
    """Stop a running dashboard subprocess."""
    _validate_dashboard_id(dashboard_id)

    if dashboard_id not in running_dashboards:
        _restore_status_from_disk(dashboard_id)

    if dashboard_id not in running_dashboards:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    _stop_dashboard_process(dashboard_id)
    return {"message": "Dashboard stopped"}


@app.get("/download-dashboard/{dashboard_id}")
async def download_dashboard(dashboard_id: str):
    """Download the generated dashboard Python code file."""
    _validate_dashboard_id(dashboard_id)

    info = running_dashboards.get(dashboard_id) or _restore_status_from_disk(dashboard_id)
    dashboard_dir = Path(info.get("dashboard_dir", DASHBOARD_ROOT / dashboard_id)) if info else DASHBOARD_ROOT / dashboard_id

    candidate = dashboard_dir / "dashboard_app.py"
    if candidate.exists():
        return FileResponse(str(candidate), filename=f"dashboard_{dashboard_id}.py", media_type="text/plain")

    if info and info.get("output_file") and os.path.exists(info["output_file"]):
        return FileResponse(str(info["output_file"]), filename=f"dashboard_{dashboard_id}.py", media_type="text/plain")

    raise HTTPException(status_code=404, detail="Dashboard file not found")


@app.get("/dashboard-error/{dashboard_id}")
async def get_dashboard_error(dashboard_id: str):
    """Return the latest runtime error diagnostics for a dashboard."""
    _validate_dashboard_id(dashboard_id)

    info = running_dashboards.get(dashboard_id) or _restore_status_from_disk(dashboard_id)
    dashboard_dir = Path(info.get("dashboard_dir", DASHBOARD_ROOT / dashboard_id)) if info else DASHBOARD_ROOT / dashboard_id

    error_text = None
    if (dashboard_dir / "run_error.log").exists():
        try:
            error_text = (dashboard_dir / "run_error.log").read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

    if not error_text and (dashboard_dir / "app_stderr.log").exists():
        try:
            p = dashboard_dir / "app_stderr.log"
            data = p.read_bytes()
            error_text = data[-65536:].decode(errors="ignore")
        except Exception:
            pass

    if not error_text and info:
        error_text = info.get("error", "")

    return {
        "dashboard_id": dashboard_id,
        "error": error_text or "",
        "status": (info or {}).get("status", "unknown"),
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", os.environ.get("BACKEND_PORT", "8000")))
    uvicorn.run(app, host="0.0.0.0", port=port)
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import os
import shutil
import uuid
import subprocess
import threading
import time
from pathlib import Path
import uvicorn
from typing import Optional
import sys
import json
import httpx

from app.paths import DASHBOARD_DIR, DATA_DIR, REPO_ROOT, UPLOAD_DIR, ensure_runtime_dirs
from app.services.prompt_chain_new import create_dashboard

app = FastAPI(title="Veridia Backend", version="1.0.0")

# CORS middleware for frontend communication
cors_origins_env = os.getenv("CORS_ORIGINS")
if cors_origins_env:
    origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
else:
    origins = ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173", "*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _kill_process_group(pid: Optional[int]) -> None:
    """Safely terminate a subprocess across POSIX and Windows systems."""
    if not pid:
        return
    import signal
    if hasattr(os, "killpg"):
        try:
            os.killpg(pid, signal.SIGTERM)
            time.sleep(0.4)
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
            time.sleep(0.4)
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


# Ensuring directories exist
ensure_runtime_dirs()
DASHBOARD_ROOT = DASHBOARD_DIR

# Store running dashboards
running_dashboards = {}

# Map Dash ports to stable paths that Nginx reverse-proxies
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

def _status_file_for(dashboard_dir: Path) -> Path:
    return dashboard_dir / "status.json"

def _save_status(dashboard_id: str):
    try:
        info = running_dashboards.get(dashboard_id)
        if not info:
            return
        dashboard_dir = Path(info.get("dashboard_dir", ""))
        if not dashboard_dir:
            return
        with open(_status_file_for(dashboard_dir), "w") as f:
            json.dump(info, f)
    except Exception as _:
        pass

# Pipeline stage tracking
pipeline_stages = {
    "stage_1": "Analyzing your dataset comprehensively",
    "stage_2": "Searching for similar visualization examples", 
    "stage_3": "Designing your dashboard layout",
    "stage_4": "Generating interactive visualization code",
    "stage_5": "Optimizing code for best performance",
    "stage_6": "Testing and correcting any errors"
}

@app.get("/")
async def root():
    return {"message": "Veridia Backend API", "status": "running"}

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
        "upload_dir_exists": UPLOAD_DIR.exists(),
        "dashboard_dir_exists": DASHBOARD_ROOT.exists(),
    }

@app.get("/data/{filename}")
async def download_dataset(filename: str):
    """Serve sample datasets from data folders.
    Search order:
    1) <repo>/backend/data
    2) <repo>/data
    """
    try:
        candidates = [
            DATA_DIR.resolve(),
            (REPO_ROOT / "data").resolve(),
        ]

        found_path = None
        for data_dir in candidates:
            candidate = (data_dir / filename).resolve()
            # Prevent path traversal: ensure candidate within data_dir
            if data_dir in candidate.parents and candidate.exists() and candidate.is_file():
                found_path = candidate
                break

        if not found_path:
            raise HTTPException(status_code=404, detail="Dataset not found")

        return FileResponse(str(found_path), media_type="text/csv", filename=filename)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to serve dataset: {e}")

@app.post("/upload-dataset")
async def upload_dataset(file: UploadFile = File(...)):
    """Upload a dataset file (CSV)"""
    try:
        # Validate file type
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="Only CSV files are supported")
        
        # Generate unique ID for the file
        file_id = str(uuid.uuid4())
        file_path = UPLOAD_DIR / f"{file_id}.csv"
        
        # Save the file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return {
            "file_id": file_id,
            "filename": file.filename,
            "file_path": str(file_path),
            "message": "Dataset uploaded successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/generate-dashboard")
async def generate_dashboard(
    background_tasks: BackgroundTasks,
    file_id: str = Form(...),
    user_prompt: str = Form(...)
):
    """Generate dashboard using the prompt chain"""
    try:
        print(f"[generate-dashboard] Received file_id={file_id}")
        # Verify GROQ_API_KEY
        if not os.getenv("GROQ_API_KEY"):
            raise HTTPException(
                status_code=400,
                detail="GROQ_API_KEY is not configured. Please set your GROQ_API_KEY in backend/.env.local or your environment variables."
            )

        # Find the uploaded file
        file_path = UPLOAD_DIR / f"{file_id}.csv"
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Dataset not found at {file_path}")
        
        # Generate unique dashboard ID
        dashboard_id = str(uuid.uuid4())
        dashboard_dir = DASHBOARD_ROOT / dashboard_id
        dashboard_dir.mkdir(exist_ok=True)
        
        # Initialize dashboard status immediately (prevents 404 during early polling)
        running_dashboards[dashboard_id] = {
            "status": "generating",
            "current_stage": "stage_1",
            "stage_progress": 0,
            "output_file": None,
            "dashboard_dir": str(dashboard_dir)
        }
        _save_status(dashboard_id)

        # Copy dataset to dashboard directory
        dataset_path = dashboard_dir / "dataset.csv"
        try:
            shutil.copy2(file_path, dataset_path)
        except Exception as copy_err:
            raise HTTPException(status_code=500, detail=f"Failed to copy dataset to dashboard dir: {copy_err}")
        
        # Run dashboard generation in background
        background_tasks.add_task(
            run_dashboard_generation,
            dataset_path,
            user_prompt,
            dashboard_dir,
            dashboard_id
        )
        
        return {
            "dashboard_id": dashboard_id,
            "status": "generating",
            "message": "Dashboard generation started"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        # Surface detailed error for easier debugging on frontend
        raise HTTPException(status_code=500, detail=f"Generation failed: {type(e).__name__}: {str(e)}")

def run_dashboard_generation(dataset_path: Path, user_prompt: str, dashboard_dir: Path, dashboard_id: str):
    """Run the dashboard generation pipeline"""
    try:
        # Initialize dashboard status with first stage
        running_dashboards[dashboard_id] = {
            "status": "generating",
            "current_stage": "stage_1",
            "stage_progress": 0,
            "output_file": None,
            "dashboard_dir": str(dashboard_dir)
        }
        
        # Define a progress callback to receive stage updates from the prompt chain
        def _on_progress(stage: str, progress: int, note: str | None = None):
            try:
                running_dashboards[dashboard_id]["current_stage"] = stage
                running_dashboards[dashboard_id]["stage_progress"] = progress
                if note is not None:
                    running_dashboards[dashboard_id]["stage_note"] = note
                _save_status(dashboard_id)
            except Exception:
                # Avoid crashing background thread on telemetry issues
                pass

        # Seed UI with the very first stage
        _on_progress("stage_1", 16, "Starting comprehensive analysis of your dataset…")
        
        print(f"[{dashboard_id}] Starting dashboard generation...")
        print(f"[{dashboard_id}] Dataset path: {dataset_path}")
        print(f"[{dashboard_id}] Output dir: {dashboard_dir}")
        print(f"[{dashboard_id}] User prompt: {user_prompt[:100]}...")

        # Run the prompt chain
        output_file = create_dashboard(
            str(dataset_path),
            user_prompt,
            str(dashboard_dir),
            dashboard_id,
            progress_cb=_on_progress,
        )
        
        print(f"[{dashboard_id}] create_dashboard returned: {output_file}")
        
        if not output_file:
            raise ValueError("create_dashboard returned empty output_file")
        
        if not os.path.exists(output_file):
            raise FileNotFoundError(f"Generated output file does not exist: {output_file}")
        
        # Update status to completed
        running_dashboards[dashboard_id].update({
            "status": "completed",
            "output_file": output_file,
            "current_stage": "stage_6",
            "stage_progress": 100
        })
        _save_status(dashboard_id)
        
        print(f"Dashboard {dashboard_id} generated successfully")
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        running_dashboards[dashboard_id] = {
            "status": "failed",
            "error": f"{type(e).__name__}: {str(e)}",
            "error_trace": error_trace,
            "current_stage": "failed",
            "stage_progress": 0,
            "dashboard_dir": str(dashboard_dir)
        }
        print(f"Dashboard {dashboard_id} generation failed: {e}")
        print(f"Traceback:\n{error_trace}")
        _save_status(dashboard_id)

@app.get("/dashboard-status/{dashboard_id}")
async def get_dashboard_status(dashboard_id: str):
    """Get the status of dashboard generation"""
    if dashboard_id not in running_dashboards:
        # Try to restore from disk (helps across server reloads)
        dashboard_dir = DASHBOARD_ROOT / dashboard_id
        status_file = _status_file_for(dashboard_dir)
        if status_file.exists():
            try:
                with open(status_file) as f:
                    info = json.load(f)
                running_dashboards[dashboard_id] = info
            except Exception:
                pass
        else:
            # If directory exists but no status, return minimal info instead of 404
            if dashboard_dir.exists():
                return {
                    "status": "unknown",
                    "dashboard_dir": str(dashboard_dir),
                    "current_stage": "unknown",
                    "stage_progress": 0
                }
            raise HTTPException(status_code=404, detail="Dashboard not found")
    return running_dashboards[dashboard_id]

@app.post("/run-dashboard/{dashboard_id}")
async def run_dashboard(dashboard_id: str, request: Request):
    """Start the Dash app for a generated dashboard"""
    try:
        if dashboard_id not in running_dashboards:
            # Try to restore from disk similar to /dashboard-status
            dashboard_dir = DASHBOARD_ROOT / dashboard_id
            status_file = _status_file_for(dashboard_dir)
            if status_file.exists():
                try:
                    with open(status_file) as f:
                        info = json.load(f)
                    running_dashboards[dashboard_id] = info
                except Exception:
                    pass
            if dashboard_id not in running_dashboards:
                raise HTTPException(status_code=404, detail="Dashboard not found")
        
        dashboard_info = running_dashboards[dashboard_id]
        if dashboard_info["status"] != "completed":
            raise HTTPException(status_code=400, detail="Dashboard not ready")
        
        # Start the Dash app using the same Python interpreter as the backend
        dashboard_dir = Path(dashboard_info["dashboard_dir"])
        output_file = dashboard_info.get("output_file")
        
        # Determine the actual code file path
        code_path = None
        if output_file and os.path.exists(output_file):
            code_path = Path(output_file)
        else:
            # Try common dashboard file names
            candidates = [
                dashboard_dir / "dashboard_app.py",
                dashboard_dir / f"dashboard_{dashboard_id}.py",
            ]
            for candidate in candidates:
                if candidate.exists():
                    code_path = candidate
                    break
            if not code_path:
                raise HTTPException(status_code=404, detail="Dashboard code file not found in directory")
        
        port = find_available_port(8050, 8060)
        script_name = code_path.name  # ensure we run file within cwd

        # for deployed version comment out
        # # Build base_path and external URL before launch so we can pass BASE_PATH to the child
        # scheme = request.headers.get("X-Forwarded-Proto") or request.url.scheme
        # host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or "localhost"
        # host_name = host.split(":")[0]
        # base_path = PORT_PATH_MAP.get(port, f"/dash{port-8049}/")
        # For local development, use direct port URL (no reverse proxy path)
        external_url = f"http://localhost:{port}"
        
        # Use sys.executable to ensure same environment
        cmd = [sys.executable, script_name]

        # Start process with pipes so we can inspect initial errors
        # Start subprocess in its own process group so we can terminate reliably
        import signal
        # Set PORT only (no BASE_PATH for local dev - Dash will mount at /)
        child_env = {**os.environ, "PORT": str(port)}

        # for deployed version comment out
        # # Set PORT and BASE_PATH so Dash mounts under the reverse-proxy subpath
        # child_env = {**os.environ, "PORT": str(port), "BASE_PATH": base_path}

        process = subprocess.Popen(
            cmd,
            cwd=dashboard_dir,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **_get_process_creation_kwargs()
        )

        try:
            # Give the process a short time to fail loudly if there's a startup error
            stdout_bytes, stderr_bytes = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # Process is still running -> detach and stream logs to files
            # Create log files and stream remaining output in background threads
            stdout_log = open(dashboard_dir / "app_stdout.log", "ab")
            stderr_log = open(dashboard_dir / "app_stderr.log", "ab")

            def stream_pipe(pipe, target_file):
                try:
                    for chunk in iter(lambda: pipe.read(1024), b""):
                        if not chunk:
                            break
                        target_file.write(chunk)
                        target_file.flush()
                except Exception:
                    pass
                finally:
                    try:
                        pipe.close()
                    except Exception:
                        pass

            # Start streaming threads
            if process.stdout:
                t_out = threading.Thread(target=stream_pipe, args=(process.stdout, stdout_log), daemon=True)
                t_out.start()
            if process.stderr:
                t_err = threading.Thread(target=stream_pipe, args=(process.stderr, stderr_log), daemon=True)
                t_err.start()

            # Mark running
            running_dashboards[dashboard_id]["running"] = True
            running_dashboards[dashboard_id]["port"] = port
            running_dashboards[dashboard_id]["process"] = process.pid
            running_dashboards[dashboard_id]["output_file"] = str(code_path) #for local
            
            # for deployed version comment out
            # # Build external URL using request headers (supports EC2/Nginx via X-Forwarded-Proto)
            # scheme = request.headers.get("X-Forwarded-Proto") or request.url.scheme
            # host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or "localhost"
            # host_name = host.split(":")[0]
            # base_path = PORT_PATH_MAP.get(port, f"/dash{port-8049}/")
            # external_url = f"{scheme}://{host_name}{base_path}"
            # running_dashboards[dashboard_id]["url"] = external_url
            # # Also persist base_path for clients that need to embed
            # running_dashboards[dashboard_id]["base_path"] = base_path
            
            running_dashboards[dashboard_id]["url"] = external_url
            
            # for deployed version
            # # Also persist base_path for clients that need to embed
            # running_dashboards[dashboard_id]["base_path"] = base_path
            _save_status(dashboard_id)

            return {
                "dashboard_id": dashboard_id,
                "status": "running",
                "url": external_url,
                "port": port
            }

        # If we got here the process exited within the timeout window
        stderr_text = (stderr_bytes or b"").decode(errors="ignore")
        stdout_text = (stdout_bytes or b"").decode(errors="ignore")

        # Persist logs for debugging
        try:
            with open(dashboard_dir / "app_stderr.log", "ab") as f:
                f.write((stderr_bytes or b"")[:100000])
        except Exception:
            pass
        try:
            with open(dashboard_dir / "app_stdout.log", "ab") as f:
                f.write((stdout_bytes or b"")[:100000])
        except Exception:
            pass

        # Also persist a combined run_error.log so the fixer and frontend can retrieve detailed context
        try:
            with open(dashboard_dir / "run_error.log", "w") as f:
                f.write("STDOUT:\n")
                f.write(stdout_text or "")
                f.write("\n\nSTDERR:\n")
                f.write(stderr_text or "")
        except Exception:
            pass

        # Update status with the error and mark as needing a fix
        running_dashboards[dashboard_id].update({
            "running": False,
            "port": None,
            "status": "failed",
            "error": stderr_text or "Dashboard failed to start (no stderr captured)",
            "needs_fix": True
        })
        _save_status(dashboard_id)

        # Save an error file to the dashboard dir for the LLM fixer
        try:
            with open(dashboard_dir / "run_error.log", "w") as f:
                f.write("STDOUT:\n")
                f.write(stdout_text or "")
                f.write("\n\nSTDERR:\n")
                f.write(stderr_text or "")
        except Exception:
            pass

        # Return error to frontend so it can trigger a fix request (or call /fix-dashboard endpoint)
        raise HTTPException(status_code=500, detail="Failed to start dashboard. Error captured and saved; call /fix-dashboard/{dashboard_id} to attempt auto-fix.")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run dashboard: {str(e)}")

@app.get("/stop-dashboard/{dashboard_id}")
async def stop_dashboard(dashboard_id: str):
    """Stop a running dashboard"""
    try:
        if dashboard_id not in running_dashboards:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        
        dashboard_info = running_dashboards[dashboard_id]
        if not dashboard_info.get("running"):
            return {"message": "Dashboard not running"}
        
        # Stop the process by PID / process group (more reliable than pkill by pattern)
        import signal
        pid = dashboard_info.get("process")
        if pid:
            _kill_process_group(pid)
        
        running_dashboards[dashboard_id]["running"] = False
        running_dashboards[dashboard_id]["port"] = None
        running_dashboards[dashboard_id]["process"] = None
        _save_status(dashboard_id)
        
        return {"message": "Dashboard stopped"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop dashboard: {str(e)}")


@app.post("/fix-dashboard/{dashboard_id}")
async def fix_dashboard(dashboard_id: str, request: Request):
    """Attempt to automatically fix generated dashboard code using LLM helper and re-run it."""
    try:
        if dashboard_id not in running_dashboards:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        dashboard_info = running_dashboards[dashboard_id]
        dashboard_dir = Path(dashboard_info.get("dashboard_dir", ""))
        output_file = dashboard_info.get("output_file")
        if not output_file:
            raise HTTPException(status_code=400, detail="No generated dashboard file available to fix")

        # Import the LLM fixer from prompt chain (safe import)
        from app.services.prompt_chain_new import fix_generated_code

        # Read error log
        error_text = ""
        try:
            with open(dashboard_dir / "run_error.log", "r") as f:
                error_text = f.read()
        except Exception:
            error_text = dashboard_info.get("error", "")

        fixed = fix_generated_code(str(Path(output_file)), error_text, str(dashboard_dir))

        if not fixed:
            # LLM not configured or failed to return a fix
            raise HTTPException(status_code=500, detail="Auto-fix failed or not configured; see run_error.log in dashboard directory")

        # Overwrite the existing dashboard file with the fixed code
        try:
            with open(dashboard_dir / Path(output_file).name, "w", encoding="utf-8") as f:
                f.write(fixed)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to write fixed code: {e}")

        # Prepare to (re)launch the fixed app
        #  for deployed
        # scheme = request.headers.get("X-Forwarded-Proto") or request.url.scheme
        # host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or "localhost"
        # host_name = host.split(":")[0]
        # port = find_available_port(8050, 8060)
        # base_path = PORT_PATH_MAP.get(port, f"/dash{port-8049}/")
        # external_url = f"{scheme}://{host_name}{base_path}"
        port = find_available_port(8050, 8060)
        # for local
        external_url = f"http://localhost:{port}"

        dashboard_dir = Path(dashboard_info["dashboard_dir"])
        output_file = dashboard_info["output_file"]
        script_name = Path(output_file).name
        cmd = [sys.executable, script_name]
        env = {**os.environ, "PORT": str(port)}

        process = subprocess.Popen(
            cmd,
            cwd=dashboard_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **_get_process_creation_kwargs()
        )

        try:
            stdout_bytes, stderr_bytes = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # stream logs to files
            stdout_log = open(dashboard_dir / "app_stdout.log", "ab")
            stderr_log = open(dashboard_dir / "app_stderr.log", "ab")

            def stream_pipe(pipe, target_file):
                try:
                    for chunk in iter(lambda: pipe.read(1024), b""):
                        if not chunk:
                            break
                        target_file.write(chunk)
                        target_file.flush()
                except Exception:
                    pass
                finally:
                    try:
                        pipe.close()
                    except Exception:
                        pass

            if process.stdout:
                t_out = threading.Thread(target=stream_pipe, args=(process.stdout, stdout_log), daemon=True)
                t_out.start()
            if process.stderr:
                t_err = threading.Thread(target=stream_pipe, args=(process.stderr, stderr_log), daemon=True)
                t_err.start()

            running_dashboards[dashboard_id].update({
                "running": True,
                "port": port,
                "process": process.pid,
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
                "port": port
            }

        # If process exited quickly, capture logs and return error
        stderr_text = (stderr_bytes or b"").decode(errors="ignore")
        stdout_text = (stdout_bytes or b"").decode(errors="ignore")
        try:
            with open(dashboard_dir / "app_stderr.log", "ab") as f:
                f.write((stderr_bytes or b"")[:100000])
        except Exception:
            pass
        try:
            with open(dashboard_dir / "app_stdout.log", "ab") as f:
                f.write((stdout_bytes or b"")[:100000])
        except Exception:
            pass

        running_dashboards[dashboard_id].update({
            "running": False,
            "port": None,
            "status": "failed",
            "error": stderr_text or "Dashboard failed to start after fix",
            "needs_fix": True
        })
        _save_status(dashboard_id)

        raise HTTPException(status_code=500, detail="Failed to start dashboard after fix. See logs in dashboard directory.")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fix attempt failed: {e}")

@app.post("/chat-edit/{dashboard_id}")
async def chat_edit_dashboard(dashboard_id: str, request: Request):
    """Apply a minimal LLM-driven edit to the existing dashboard code based on a user prompt,
    write the updated code, and (re)launch the Dash app.
    Expects JSON body: { "message": "<edit request>" }
    Returns: { dashboard_id, status, url, port, code }
    """
    try:
        # Restore dashboard info from disk if missing
        if dashboard_id not in running_dashboards:
            dashboard_dir = DASHBOARD_ROOT / dashboard_id
            status_file = _status_file_for(dashboard_dir)
            if status_file.exists():
                try:
                    with open(status_file) as f:
                        running_dashboards[dashboard_id] = json.load(f)
                except Exception:
                    pass
        if dashboard_id not in running_dashboards:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        payload = await request.json()
        user_message = (payload or {}).get("message")
        if not isinstance(user_message, str) or not user_message.strip():
            raise HTTPException(status_code=400, detail="'message' is required in request body")

        info = running_dashboards[dashboard_id]
        dashboard_dir = Path(info.get("dashboard_dir", ""))
        if not dashboard_dir or not dashboard_dir.exists():
            raise HTTPException(status_code=404, detail="Dashboard directory not found")

        # Determine main code path
        output_file = info.get("output_file")
        if output_file and os.path.exists(output_file):
            code_path = Path(output_file)
        else:
            candidate = dashboard_dir / "dashboard_app.py"
            if not candidate.exists():
                raise HTTPException(status_code=404, detail="Dashboard code file not found")
            code_path = candidate

        # Load existing code
        try:
            existing_code = code_path.read_text(encoding="utf-8")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read code: {e}")

        # Optional analysis context (if present)
        analysis_path = dashboard_dir / "analysis_result.json"
        dataset_summary_path = dashboard_dir / "dataset_summary.json"
        analysis_result = {}
        dataset_summary = {}
        try:
            if analysis_path.exists():
                analysis_result = json.loads(analysis_path.read_text())
        except Exception:
            analysis_result = {}
        try:
            if dataset_summary_path.exists():
                dataset_summary = json.loads(dataset_summary_path.read_text())
        except Exception:
            dataset_summary = {}

        # Import the chat edit helper lazily
        from app.services.prompt_chain_new import apply_user_edit_minimal, _validate_code

        updated_code = apply_user_edit_minimal(
            existing_code=existing_code,
            user_request=user_message,
            dataset_summary=dataset_summary,
            analysis_result=analysis_result,
        )

        # Validate and write updated code
        ok, err = _validate_code(updated_code)
        if not ok:
            raise HTTPException(status_code=500, detail=f"Model returned invalid code: {err}")
        try:
            code_path.write_text(updated_code, encoding="utf-8")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to write updated code: {e}")

        # Stop existing process if running
        try:
            if info.get("running") and info.get("process"):
                _kill_process_group(info.get("process"))
                info["running"] = False
                info["process"] = None
                info["port"] = None
        except Exception:
            pass
        

        # for deployed
        # scheme = request.headers.get("X-Forwarded-Proto") or request.url.scheme
        # host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or "localhost"
        # host_name = host.split(":")[0]
        # port = find_available_port(8050, 8060)
        # base_path = PORT_PATH_MAP.get(port, f"/dash{port-8049}/")
        # external_url = f"{scheme}://{host_name}{base_path}"

        # script_name = code_path.name
        # cmd = [sys.executable, script_name]
        # # Ensure Dash app binds to the computed port and subpath for Nginx path-based proxying
        # env = {**os.environ, "PORT": str(port), "BASE_PATH": base_path}
        # Launch updated app on a fresh port
        port = find_available_port(8050, 8060)
        external_url = f"http://localhost:{port}"

        script_name = code_path.name
        cmd = [sys.executable, script_name]
        # Set PORT only for local development
        env = {**os.environ, "PORT": str(port)}

        process = subprocess.Popen(
            cmd,
            cwd=dashboard_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **_get_process_creation_kwargs()
        )

        try:
            stdout_bytes, stderr_bytes = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # stream to logs & mark running
            stdout_log = open(dashboard_dir / "app_stdout.log", "ab")
            stderr_log = open(dashboard_dir / "app_stderr.log", "ab")

            def stream_pipe(pipe, target_file):
                try:
                    for chunk in iter(lambda: pipe.read(1024), b""):
                        if not chunk:
                            break
                        target_file.write(chunk)
                        target_file.flush()
                except Exception:
                    pass
                finally:
                    try:
                        pipe.close()
                    except Exception:
                        pass

            if process.stdout:
                threading.Thread(target=stream_pipe, args=(process.stdout, stdout_log), daemon=True).start()
            if process.stderr:
                threading.Thread(target=stream_pipe, args=(process.stderr, stderr_log), daemon=True).start()

            running_dashboards[dashboard_id].update({
                "running": True,
                "port": port,
                "process": process.pid,
                "url": external_url,
                "base_path": base_path,
                "status": "running",
                "output_file": str(code_path),
            })
            _save_status(dashboard_id)

            return {
                "dashboard_id": dashboard_id,
                "status": "running",
                "url": external_url,
                "port": port,
                "code": updated_code,
            }

        # If the process exited quickly, capture logs and return error
        stderr_text = (stderr_bytes or b"").decode(errors="ignore")
        stdout_text = (stdout_bytes or b"").decode(errors="ignore")
        try:
            with open(dashboard_dir / "app_stderr.log", "ab") as f:
                f.write((stderr_bytes or b"")[:100000])
        except Exception:
            pass
        try:
            with open(dashboard_dir / "app_stdout.log", "ab") as f:
                f.write((stdout_bytes or b"")[:100000])
        except Exception:
            pass

        running_dashboards[dashboard_id].update({
            "running": False,
            "port": None,
            "status": "failed",
            "error": stderr_text or "Dashboard failed to start after chat edit",
            "needs_fix": True,
            "output_file": str(code_path),
        })
        _save_status(dashboard_id)
        raise HTTPException(status_code=500, detail="Failed to start dashboard after chat edit. See logs.")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat edit failed: {e}")

@app.post("/update-code/{dashboard_id}")
async def update_code_and_run(dashboard_id: str, request: Request):
    """Write user-edited code to the dashboard file and (re)launch the Dash app.
    Expects JSON body: { "code": "<python>" }
    Returns: { dashboard_id, status, url, port, code }
    """
    try:
        # Ensure dashboard info is available (restore from disk if needed)
        if dashboard_id not in running_dashboards:
            dashboard_dir = DASHBOARD_ROOT / dashboard_id
            status_file = _status_file_for(dashboard_dir)
            if status_file.exists():
                try:
                    with open(status_file) as f:
                        running_dashboards[dashboard_id] = json.load(f)
                except Exception:
                    pass
        if dashboard_id not in running_dashboards:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        payload = await request.json()
        code = (payload or {}).get("code")
        if not isinstance(code, str) or not code.strip():
            raise HTTPException(status_code=400, detail="'code' is required in request body")

        info = running_dashboards[dashboard_id]
        dashboard_dir = Path(info.get("dashboard_dir", ""))
        if not dashboard_dir or not dashboard_dir.exists():
            raise HTTPException(status_code=404, detail="Dashboard directory not found")

        # Determine main code path
        output_file = info.get("output_file")
        if output_file and os.path.exists(output_file):
            code_path = Path(output_file)
        else:
            code_path = dashboard_dir / "dashboard_app.py"
        # Write updated code
        try:
            code_path.write_text(code, encoding="utf-8")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to write updated code: {e}")

        # Stop existing process if running
        try:
            if info.get("running") and info.get("process"):
                _kill_process_group(info.get("process"))
                info["running"] = False
                info["process"] = None
                info["port"] = None
        except Exception:
            pass
        
        #  for deployed
        # # Launch updated app under a stable reverse-proxy subpath (consistent with run and chat-edit)
        # scheme = request.headers.get("X-Forwarded-Proto") or request.url.scheme
        # host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or "localhost"
        # host_name = host.split(":")[0]
        # port = find_available_port(8050, 8060)
        # base_path = PORT_PATH_MAP.get(port, f"/dash{port-8049}/")
        # external_url = f"{scheme}://{host_name}{base_path}"

        # script_name = Path(code_path).name
        # cmd = [sys.executable, script_name]
        # # Ensure Dash app mounts under the computed subpath via BASE_PATH
        # env = {**os.environ, "PORT": str(port), "BASE_PATH": base_path}
        # Launch updated app on a fresh port
        port = find_available_port(8050, 8060)
        external_url = f"http://localhost:{port}"

        script_name = Path(code_path).name
        cmd = [sys.executable, script_name]
        # Set PORT only for local development
        env = {**os.environ, "PORT": str(port)}

        process = subprocess.Popen(
            cmd,
            cwd=dashboard_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **_get_process_creation_kwargs()
        )

        try:
            stdout_bytes, stderr_bytes = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # Stream to logs & mark running
            stdout_log = open(dashboard_dir / "app_stdout.log", "ab")
            stderr_log = open(dashboard_dir / "app_stderr.log", "ab")

            def stream_pipe(pipe, target_file):
                try:
                    for chunk in iter(lambda: pipe.read(1024), b""):
                        if not chunk:
                            break
                        target_file.write(chunk)
                        target_file.flush()
                except Exception:
                    pass
                finally:
                    try:
                        pipe.close()
                    except Exception:
                        pass

            if process.stdout:
                threading.Thread(target=stream_pipe, args=(process.stdout, stdout_log), daemon=True).start()
            if process.stderr:
                threading.Thread(target=stream_pipe, args=(process.stderr, stderr_log), daemon=True).start()

            running_dashboards[dashboard_id].update({
                "running": True,
                "port": port,
                "process": process.pid,
                "url": external_url,
                "base_path": base_path,
                "status": "running",
                "output_file": str(code_path),
            })
            _save_status(dashboard_id)

            return {
                "dashboard_id": dashboard_id,
                "status": "running",
                "url": external_url,
                "port": port,
                "code": code,
            }

        # If the process exited quickly, capture logs and return error
        stderr_text = (stderr_bytes or b"").decode(errors="ignore")
        stdout_text = (stdout_bytes or b"").decode(errors="ignore")
        try:
            with open(dashboard_dir / "app_stderr.log", "ab") as f:
                f.write((stderr_bytes or b"")[:100000])
        except Exception:
            pass
        try:
            with open(dashboard_dir / "app_stdout.log", "ab") as f:
                f.write((stdout_bytes or b"")[:100000])
        except Exception:
            pass

        running_dashboards[dashboard_id].update({
            "running": False,
            "port": None,
            "status": "failed",
            "error": stderr_text or "Dashboard failed to start after manual update",
            "needs_fix": True,
            "output_file": str(code_path),
        })
        _save_status(dashboard_id)
        raise HTTPException(status_code=500, detail="Failed to start dashboard after manual update. See logs.")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Manual code update failed: {e}")

@app.get("/download-dashboard/{dashboard_id}")
async def download_dashboard(dashboard_id: str):
    """Download the generated dashboard code"""
    try:
        # Try to get dashboard info from memory
        dashboard_info = running_dashboards.get(dashboard_id)

        # If not in memory, try to restore from disk
        if not dashboard_info:
            dashboard_dir = DASHBOARD_ROOT / dashboard_id
            status_file = _status_file_for(dashboard_dir)
            if status_file.exists():
                try:
                    with open(status_file) as f:
                        dashboard_info = json.load(f)
                except Exception:
                    dashboard_info = None

        # If we still don't have dashboard_info, try to locate the dashboard directory directly
        if not dashboard_info:
            dashboard_dir = DASHBOARD_ROOT / dashboard_id
            candidate = dashboard_dir / "dashboard_app.py"
            if candidate.exists():
                return FileResponse(str(candidate), filename=f"dashboard_{dashboard_id}.py", media_type="text/plain")
            raise HTTPException(status_code=404, detail="Dashboard not found")

        # If we have info but not completed, still allow downloading the code file if it exists
        output_file = dashboard_info.get("output_file")
        if not output_file:
            # Try default location inside dashboard_dir
            dashboard_dir = Path(dashboard_info.get("dashboard_dir", DASHBOARD_ROOT / dashboard_id))
            candidate = dashboard_dir / "dashboard_app.py"
            if candidate.exists():
                return FileResponse(str(candidate), filename=f"dashboard_{dashboard_id}.py", media_type="text/plain")
            raise HTTPException(status_code=404, detail="Dashboard file not found")

        if not os.path.exists(output_file):
            # Try to resolve relative to dashboard_dir
            dashboard_dir = Path(dashboard_info.get("dashboard_dir", DASHBOARD_ROOT / dashboard_id))
            candidate = dashboard_dir / Path(output_file).name
            if candidate.exists():
                return FileResponse(str(candidate), filename=f"dashboard_{dashboard_id}.py", media_type="text/plain")
            raise HTTPException(status_code=404, detail="Dashboard file not found")

        return FileResponse(str(output_file), filename=f"dashboard_{dashboard_id}.py", media_type="text/plain")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

def find_available_port(start_port: int, end_port: int) -> int:
    """Find an available port in the given range"""
    import socket
    
    for port in range(start_port, end_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    
    raise RuntimeError("No available ports found")


@app.get("/dashboard-error/{dashboard_id}")
async def get_dashboard_error(dashboard_id: str):
    """Return the latest, most detailed error text for a dashboard run.
    Prefers run_error.log, then app_stderr.log, then in-memory status error.
    """
    try:
        # Try to get dashboard info and directory
        info = running_dashboards.get(dashboard_id)
        dashboard_dir = None
        if info:
            dashboard_dir = Path(info.get("dashboard_dir", ""))
        if not info or not dashboard_dir or not dashboard_dir.exists():
            # Try restore from disk
            dashboard_dir = DASHBOARD_ROOT / dashboard_id
            status_file = _status_file_for(dashboard_dir)
            if status_file.exists():
                try:
                    with open(status_file) as f:
                        info = json.load(f)
                except Exception:
                    info = None

        # Attempt to read files in order of richness
        error_text = None
        if dashboard_dir and (dashboard_dir / "run_error.log").exists():
            try:
                error_text = (dashboard_dir / "run_error.log").read_text(encoding="utf-8", errors="ignore")
            except Exception:
                error_text = None
        if not error_text and dashboard_dir and (dashboard_dir / "app_stderr.log").exists():
            try:
                
                p = dashboard_dir / "app_stderr.log"
                data = p.read_bytes()
                error_text = data[-65536:].decode(errors="ignore")
            except Exception:
                error_text = None
        if not error_text and info:
            error_text = info.get("error")

        return {"dashboard_id": dashboard_id, "error": error_text or "", "status": (info or {}).get("status", "unknown")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read dashboard error: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 
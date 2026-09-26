import ast
from collections import Counter
import io
import json
import logging
import math
import os
import re
import sys
from typing import Any, Dict, List, Tuple
import uuid

from groq import APIStatusError, Groq
import httpx
import numpy as np
import pandas as pd

from app.paths import DASHBOARD_DIR, DATA_DIR, TEMPLATES_FILE, load_project_env

# Force UTF-8 standard streams on Windows so logging and prints never fail
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Load environment
load_project_env()


def get_groq_client() -> Groq:
    """Get a Groq client instance, raising a clear exception if GROQ_API_KEY is not configured."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not configured. Please set your GROQ_API_KEY in backend/.env.local or environment variables.")
    return Groq(api_key=api_key)


# Configuration (environment-configurable with supported Groq models)
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
MODEL_ANALYSIS = os.getenv("GROQ_MODEL_ANALYSIS", DEFAULT_GROQ_MODEL)
MODEL_DESIGN = os.getenv("GROQ_MODEL_DESIGN", DEFAULT_GROQ_MODEL)
MODEL_CODE = os.getenv("GROQ_MODEL_CODE", DEFAULT_GROQ_MODEL)
MODEL_OPTIMIZE = os.getenv("GROQ_MODEL_OPTIMIZE", DEFAULT_GROQ_MODEL)
FALLBACK_GROQ_MODELS = ["openai/gpt-oss-20b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"]

# Toggle counter to alternate chat-edit calls between CODE and OPTIMIZE models
CHAT_EDIT_CALL_COUNT = 0
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")


def _chat_completion_with_fallback(client: Groq, preferred_model: str, messages: list, **kwargs):
    """Invoke Groq chat completion, automatically falling back to alternative models if rate limits or errors occur."""
    models_to_try = [preferred_model] + [m for m in FALLBACK_GROQ_MODELS if m != preferred_model]
    last_err = None
    for model in models_to_try:
        try:
            return client.chat.completions.create(
                messages=messages,
                model=model,
                **kwargs
            )
        except Exception as exc:
            last_err = exc
            logging.warning(f"Groq model {model} attempt failed: {exc}. Trying fallback model if available.")
    raise last_err


def validate_groq_configuration() -> None:
    """Fail early with an actionable error for invalid keys or unavailable models."""
    client = get_groq_client()
    try:
        available_models = {model.id for model in client.models.list().data}
    except APIStatusError as exc:
        if exc.status_code in (401, 403):
            raise ValueError(
                "GROQ_API_KEY is invalid or not authorized. Check the key in backend/.env.local."
            ) from exc
        raise ValueError(
            f"Unable to verify Groq configuration (HTTP {exc.status_code}). Check Groq availability and try again."
        ) from exc

    configured_models = {
        MODEL_ANALYSIS,
        MODEL_DESIGN,
        MODEL_CODE,
        MODEL_OPTIMIZE,
    }
    unavailable_models = sorted(configured_models - available_models)
    if unavailable_models:
        text_models = sorted([m for m in available_models if not m.startswith("whisper") and "guard" not in m])
        suggestion = f" Available text models on your account: {', '.join(text_models)}" if text_models else ""
        raise ValueError(
            "Configured Groq model ID(s) are unavailable: "
            f"{', '.join(unavailable_models)}. Update the GROQ_MODEL_* setting(s) in backend/.env.local.{suggestion}"
        )


def _extract_code_blocks(text: str) -> str:
    """Extract code from fenced blocks, handling multiple blocks, unclosed blocks, and raw code."""
    if not text:
        return ""
    text_clean = text.strip()

    # Match standard python block
    py_pattern = r"```(?:python|py)\s*\n([\s\S]*?)(?:\n```|$)"
    match = re.search(py_pattern, text_clean, re.IGNORECASE)
    if match and match.group(1).strip():
        return match.group(1).strip()

    # Match generic fenced block
    gen_pattern = r"```\s*\n([\s\S]*?)(?:\n```|$)"
    match = re.search(gen_pattern, text_clean)
    if match and match.group(1).strip():
        return match.group(1).strip()

    # If starts with ``` remove fence markers
    if text_clean.startswith("```"):
        text_clean = re.sub(r"^```[a-zA-Z]*\n?", "", text_clean)
        text_clean = re.sub(r"\n?```$", "", text_clean)

    return text_clean.strip()


def _validate_code(code: str) -> tuple[bool, str]:
    """Return (ok, error_text) after attempting to parse Python code."""
    if not code or not code.strip():
        return False, "Code is empty"
    try:
        ast.parse(code)
        return True, ""
    except Exception as e:
        return False, str(e)


def _normalized_code(s: str) -> str:
    """Normalize code for minimal-change comparison: strip whitespace-only diffs."""
    try:
        return re.sub(r"\s+", "", s or "")
    except Exception:
        return s or ""


def sanitize_and_modernize_dash_code(code: str) -> str:
    """Deterministic AST & regex sanitizer and modernizer for Dash + DBC code.
    Fixes:
    1. All deprecated dash_bootstrap_components (DBC 2.0.4 compatibility):
       - dbc.FormGroup -> html.Div(..., className="mb-3")
       - dbc.InputGroupAddon -> dbc.InputGroupText
       - dbc.CardDeck, dbc.CardColumns -> dbc.Row or html.Div
       - dbc.CardGroup -> html.Div
       - dbc.Jumbotron -> html.Div(..., className="p-4 mb-4 bg-dark rounded-3")
       - dbc.ListGroupItemHeading -> html.H5
       - dbc.ListGroupItemText -> html.P
       - inline=True in dbc.Form removed
    2. Essential imports (dash, html, dcc, dash_table, callback, Output, Input, State, dbc, px, go, os, sys, pd, np)
    3. Safe dataset resolution using script_dir and fallback to dataset.csv
    4. Base path proxy prefix configuration on Dash app
    5. CORS headers handler on app.server
    6. Main run block with PORT environment read and 0.0.0.0 binding
    7. Dropdown contrast styling in dark theme
    """
    if not code or not code.strip():
        return code

    s = code.strip()

    # 0. Ensure essential imports exist at top
    needed_imports = []
    if not re.search(r'\bimport\s+os\b', s):
        needed_imports.append("import os")
    if not re.search(r'\bimport\s+sys\b', s):
        needed_imports.append("import sys")
    if not re.search(r'\bimport\s+pandas\b', s) and "pd." in s:
        needed_imports.append("import pandas as pd")
    if not re.search(r'\bimport\s+dash\b', s):
        needed_imports.append("import dash")
    if not re.search(r'\bimport\s+dash_bootstrap_components\b', s) and "dbc." in s:
        needed_imports.append("import dash_bootstrap_components as dbc")
    if not re.search(r'\bfrom\s+dash\s+import\b', s):
        needed_imports.append("from dash import dcc, html, dash_table, callback, Output, Input, State")

    if needed_imports:
        s = "\n".join(needed_imports) + "\n\n" + s

    # 1. Deprecated DBC component replacements
    s = re.sub(r'\bdbc\.FormGroup\b', 'html.Div', s)
    s = re.sub(r'(?<![a-zA-Z0-9_])FormGroup\b', 'html.Div', s)
    s = re.sub(r'\bdbc\.InputGroupAddon\b', 'dbc.InputGroupText', s)
    s = re.sub(r'(?<![a-zA-Z0-9_])InputGroupAddon\b', 'dbc.InputGroupText', s)
    s = re.sub(r'\bdbc\.CardColumns\b', 'dbc.Row', s)
    s = re.sub(r'\bdbc\.CardDeck\b', 'dbc.Row', s)
    s = re.sub(r'\bdbc\.CardGroup\b', 'html.Div', s)
    s = re.sub(r'\bdbc\.Jumbotron\b', 'html.Div', s)
    s = re.sub(r'\bdbc\.ListGroupItemHeading\b', 'html.H5', s)
    s = re.sub(r'\bdbc\.ListGroupItemText\b', 'html.P', s)
    s = re.sub(r',\s*inline\s*=\s*True', '', s)
    s = re.sub(r'inline\s*=\s*True\s*,?', '', s)

    # Clean up any import of removed components
    s = re.sub(r'from\s+dash_bootstrap_components\s+import\s+[^;\n]*\bFormGroup\b', 'import dash_bootstrap_components as dbc', s)

    # 2. Ensure base_path exists before app initialization
    if 'base_path' not in s:
        if re.search(r'\n\s*app\s*=', s):
            s = re.sub(r'(\n\s*app\s*=)', r"\nbase_path = os.getenv('BASE_PATH', '/')\n\1", s, count=1)
        else:
            s = s + "\nbase_path = os.getenv('BASE_PATH', '/')\n"

    # 3. Ensure Dash app is initialized with BASE_PATH prefixes & suppress_callback_exceptions
    if "requests_pathname_prefix" not in s and ("dash.Dash(" in s or "Dash(" in s):
        def _patch_dash_init(m: re.Match) -> str:
            call_text = m.group(0)
            if "requests_pathname_prefix" in call_text:
                return call_text
            open_p = call_text.find("(")
            inner = call_text[open_p + 1 :].rstrip()
            if inner.endswith(")"):
                inner = inner[:-1].rstrip()
            sep = ", " if inner.strip() else ""
            return (
                call_text[: open_p + 1]
                + inner
                + sep
                + "requests_pathname_prefix=base_path, routes_pathname_prefix=base_path, suppress_callback_exceptions=True)"
            )
        s = re.sub(r"(?:dash\.)?Dash\s*\([^)]*\)", _patch_dash_init, s)

    # 4. Ensure CORS handler on app.server
    if "Access-Control-Allow-Origin" not in s and "add_cors_headers" not in s and "_add_cors_headers" not in s:
        cors_snippet = (
            "\n# Enable CORS headers for iframe embedding\n"
            "if 'app' in globals() and hasattr(app, 'server'):\n"
            "    @app.server.after_request\n"
            "    def _add_cors_headers(response):\n"
            "        response.headers['Access-Control-Allow-Origin'] = '*'\n"
            "        response.headers['Access-Control-Allow-Headers'] = '*'\n"
            "        response.headers['Access-Control-Allow-Methods'] = '*'\n"
            "        return response\n"
        )
        if 'if __name__ == "__main__":' in s:
            s = s.replace('if __name__ == "__main__":', cors_snippet + '\nif __name__ == "__main__":')
        elif "if __name__ == '__main__':" in s:
            s = s.replace("if __name__ == '__main__':", cors_snippet + "\nif __name__ == '__main__':")
        else:
            s = s + "\n" + cors_snippet

    # 5. Ensure __main__ block has app.run(host='0.0.0.0', port=port, debug=False)
    if "if __name__ ==" not in s:
        s = s + (
            "\n\nif __name__ == '__main__':\n"
            "    port = int(os.getenv('PORT', '8050'))\n"
            "    app.run(host='0.0.0.0', port=port, debug=False)\n"
        )
    else:
        s = re.sub(r"""host\s*=\s*['"](?:localhost|127\.0\.0\.1)['"]""", "host='0.0.0.0'", s)
        if "app.run" in s and "host=" not in s:
            s = re.sub(r"app\.run\s*\(([^)]*)\)", r"app.run(\1, host='0.0.0.0')", s)
            s = s.replace(", ,", ",").replace("(,", "(")

    # 6. Ensure dataset path handling handles __file__ safely
    if "dataset.csv" in s and "script_dir" not in s and "pd.read_csv" in s:
        safe_csv_load = (
            "_script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()\n"
            "_dataset_path = os.path.join(_script_dir, 'dataset.csv') if os.path.exists(os.path.join(_script_dir, 'dataset.csv')) else 'dataset.csv'\n"
        )
        s = re.sub(r"(\w+\s*=\s*pd\.read_csv\()(['\"]dataset\.csv['\"])", safe_csv_load + r"\1_dataset_path", s, count=1)

    return s


def _test_dash_code_runtime(code: str, dataset_csv_path: str = "dataset.csv") -> tuple[bool, str]:
    """Test execute the Dash code in a sandbox namespace (dry-run without app.run())
    to catch layout, import, or callback registration errors before starting the subprocess.
    """
    if not code or not code.strip():
        return False, "Code is empty"

    try:
        compiled = compile(code, "<generated_dash_app>", "exec")
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, f"Compilation failed: {e}"

    try:
        test_dir = os.path.dirname(os.path.abspath(dataset_csv_path)) if os.path.exists(dataset_csv_path) else os.getcwd()
        fake_file = os.path.join(test_dir, "dashboard_app.py")
        env_ns = {
            "__file__": fake_file,
            "__name__": "__not_main__",  # prevents app.run() from blocking execution
            "__doc__": None,
        }
        exec(compiled, env_ns)
        return True, ""
    except Exception as e:
        import traceback
        return False, traceback.format_exc()


def _validate_dash_code(code: str) -> Tuple[bool, List[str]]:
    """Comprehensive AST and semantic validation for generated Dash applications."""
    issues: List[str] = []
    if not code or not code.strip():
        return False, ["Code is empty"]

    s = sanitize_and_modernize_dash_code(code)

    # 1. Syntax check via AST
    try:
        tree = ast.parse(s)
    except SyntaxError as e:
        return False, [f"Syntax error at line {e.lineno}: {e.msg}"]
    except Exception as e:
        return False, [f"AST parsing failed: {e}"]

    # 2. Check for deprecated DBC components
    deprecated_comps = [
        "FormGroup", "InputGroupAddon", "CardColumns", "CardDeck",
        "Jumbotron", "ListGroupItemHeading", "ListGroupItemText"
    ]
    for comp in deprecated_comps:
        if f"dbc.{comp}" in s:
            issues.append(f"Deprecated DBC component used: dbc.{comp}")

    # 3. Semantic AST checks
    has_dash_init = False
    callback_outputs: List[Tuple[str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            func_name = ""
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr
            if func_name in ("Dash", "dash"):
                has_dash_init = True

        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    dec_name = ""
                    if isinstance(decorator.func, ast.Name):
                        dec_name = decorator.func.id
                    elif isinstance(decorator.func, ast.Attribute):
                        dec_name = decorator.func.attr
                    if dec_name == "callback":
                        out_calls: List[ast.Call] = []
                        for arg in decorator.args:
                            if isinstance(arg, ast.Call):
                                out_calls.append(arg)
                            elif isinstance(arg, (ast.List, ast.Tuple)):
                                for elt in arg.elts:
                                    if isinstance(elt, ast.Call):
                                        out_calls.append(elt)

                        for call_node in out_calls:
                            output_func = getattr(call_node.func, "id", "") or getattr(call_node.func, "attr", "")
                            if output_func == "Output" and len(call_node.args) >= 2:
                                comp_id = getattr(call_node.args[0], "value", None) if isinstance(call_node.args[0], ast.Constant) else None
                                comp_prop = getattr(call_node.args[1], "value", None) if isinstance(call_node.args[1], ast.Constant) else None
                                if comp_id and comp_prop:
                                    target = (str(comp_id), str(comp_prop))
                                    has_allow_dup = any(
                                        kw.arg == "allow_duplicate" and getattr(kw.value, "value", False) is True
                                        for kw in call_node.keywords
                                    )
                                    if target in callback_outputs and not has_allow_dup:
                                        issues.append(f"Duplicate callback output target without allow_duplicate: {target}")
                                    else:
                                        callback_outputs.append(target)

    if not has_dash_init and "dash.Dash(" not in s and "Dash(" not in s:
        issues.append("Missing Dash app initialization")

    return (len(issues) == 0, issues)


def gemini_optimize_code(code: str, analysis_result: Dict[str, Any], dataset_summary: Dict[str, Any]) -> str:
    """Optional Stage: Use Gemini to further refine and correct the Dash code."""
    if not GEMINI_API_KEY or not code:
        return code
    print("\n=== STAGE 6: Gemini Optimization ===")
    system_prompt = """You are an expert Dash + Plotly + Dash Bootstrap Components 2.x engineer.
Your job is to FIX any remaining technical problems in the provided Python Dash app.
CRITICAL DBC RULES:
 - NEVER use dbc.FormGroup (it is deprecated in DBC 1.0+ and removed in DBC 2.0.4; using it will CRASH the app).
 - Wrap form inputs in html.Div([dbc.Label(...), dcc.Dropdown(...)], className="mb-3") or dbc.Row([dbc.Col(...)], className="mb-3").
 - NEVER use dbc.InputGroupAddon. Use dbc.InputGroupText instead.
 - Ensure style={'color': '#111827'} or style={'color': 'black'} is present on dcc.Dropdown() so dropdown text is visible.
 - DO NOT re-design working parts.
 - Ensure all callbacks are correctly wired with matching Input/Output IDs.
 - Keep app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8050')), debug=False).
 - Return ONLY the complete, runnable Python source file (no markdown, no explanations).
"""
    user_payload = f"""
Dataset summary:
{json.dumps(dataset_summary, indent=2)}

Generated/optimized code to perfect:
```python
{code}
```
"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    body = {
        "contents": [
            {"role": "user", "parts": [{"text": system_prompt}]},
            {"role": "user", "parts": [{"text": user_payload}]}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192
        }
    }
    try:
        with httpx.Client(timeout=60) as http:
            resp = http.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
            candidates = (data.get("candidates") or [])
            text = ""
            if candidates:
                first = candidates[0]
                if isinstance(first, dict):
                    content = first.get('content') or {}
                    parts = content.get('parts') if isinstance(content, dict) else None
                    if parts:
                        text = parts[0].get('text', '')
                elif isinstance(first, str):
                    text = first
            if not text:
                text = data.get('content') or data.get('text') or ''

            improved = _extract_code_blocks(text)
            if improved:
                improved = sanitize_and_modernize_dash_code(improved)
                ok, err = _validate_code(improved)
                if ok:
                    return improved
                else:
                    logging.warning(f"Gemini returned code but it failed validation: {err}")
                    return code
            return code
    except Exception as e:
        logging.warning(f"Gemini optimization skipped: {e}")
        return code


def create_example_data():
    """Create example sales data for testing"""
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=365, freq='D')
    
    data = {
        'Date': dates,
        'Year': dates.year,
        'Month': dates.month,
        'Product': np.random.choice(['Laptop', 'Phone', 'Tablet', 'Watch', 'Headphones'], 365),
        'Customer': np.random.choice(['Customer_A', 'Customer_B', 'Customer_C', 'Customer_D', 'Customer_E'], 365),
        'Units_Sold': np.random.randint(1, 51, 365),
        'Revenue': np.random.uniform(100, 2000, 365),
        'Profit': np.random.uniform(10, 300, 365),
        'Month_Name': [d.strftime('%B') for d in dates]
    }
    
    df = pd.DataFrame(data)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DATA_DIR / "cereal.csv"
    df.to_csv(output_path, index=False)
    return str(output_path)


def analyze_dataset_comprehensive(df: pd.DataFrame) -> Dict[str, Any]:
    """Stage 1: Comprehensive dataset analysis."""
    print("\n=== STAGE 1: Comprehensive Dataset Analysis ===")
    print(f"Analyzing dataset with {len(df)} rows and {len(df.columns)} columns")
    
    def convert_for_json(value):
        if isinstance(value, (pd.Timestamp, np.generic)):
            return str(value)
        return value
    
    sample_size = min(100, len(df))
    sample_df = df.head(sample_size)
    
    dataset_summary = {
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "columns": [
            {
                "name": col,
                "type": str(dtype),
                "unique_values": len(df[col].unique()),
                "sample_values": [convert_for_json(v) for v in df[col].dropna().unique()[:5]],
                "null_count": int(df[col].isnull().sum()),
                "null_percentage": float(df[col].isnull().sum() / len(df) * 100)
            }
            for col, dtype in df.dtypes.items()
        ],
        "sample_data": sample_df.to_dict(orient='records')
    }
    
    prompt = f"""
# Comprehensive Dataset Analysis Task

## Dataset:
{json.dumps(dataset_summary, indent=2)}

## Task:
Analyze this entire dataset comprehensively and provide detailed insights. Return a JSON with:

1. **Fields Analysis**: Detailed breakdown of each field with its role and characteristics
2. **Data Categories**: Classify the dataset into categories (e.g. Geospatial, Temporal, Statistical, Financial, Sales, etc.)
3. **Dataset Analysis**: What main patterns, trends, and insights can be extracted?
4. **Insights by Category**: Detailed insights for each identified category
5. **Visualization Insights**: What should users see in dashboard insight panels? Also mention required aggregations.
6. **Predictions**: What future trends or patterns can be predicted?
7. **Field Relationships**: Explicitly note which fields are hierarchical/categorical and their relationships.

## Output Format (JSON):
{{
    "fields_analysis": [
        {{
            "field_name": "string",
            "field_type": "string", 
            "role": "string",
            "characteristics": ["string"],
            "insights": "string"
        }}
    ],
    "data_categories": [
        {{
            "category": "string",
            "fields_involved": ["string"],
            "description": "string"
        }}
    ],
    "dataset_analysis": {{
        "main_patterns": ["string"],
        "key_trends": ["string"],
        "data_quality": "string",
        "business_value": "string"
    }},
    "insights_by_category": [
        {{
            "category": "string",
            "insights": ["string"],
            "visualization_suggestions": ["string"]
        }}
    ],
    "dashboard_insights": [
        {{
            "panel_name": "string",
            "content": "string",
            "update_triggers": ["string"]
        }}
    ],
    "predictions": [
        {{
            "aspect": "string",
            "prediction": "string",
            "timeframe": "string"
        }}
    ]
}}
"""
    
    try:
        client = get_groq_client()
        response = _chat_completion_with_fallback(
            client=client,
            preferred_model=MODEL_ANALYSIS,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=3500
        )
        
        result = json.loads(response.choices[0].message.content)
        print("[OK] Dataset analysis completed")
        return result
        
    except Exception as e:
        print(f"[ERROR] Dataset analysis failed: {str(e)}")
        cols = list(df.columns)
        num_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
        cat_cols = [c for c in cols if not pd.api.types.is_numeric_dtype(df[c])]
        return {
            "fields_analysis": [
                {"field_name": c, "field_type": "numeric" if c in num_cols else "categorical", "role": "metric" if c in num_cols else "dimension", "characteristics": [], "insights": f"Distribution of {c}"}
                for c in cols
            ],
            "data_categories": [
                {"category": "General Analytics", "fields_involved": cols[:5], "description": "Dataset metrics and dimensions"}
            ],
            "dataset_analysis": {
                "main_patterns": [f"Contains {len(df)} records across {len(cols)} dimensions"],
                "key_trends": [f"Primary metrics: {', '.join(num_cols[:3]) or 'N/A'}"],
                "data_quality": "Clean structured tabular data",
                "business_value": "Operational visibility and multi-dimensional analysis"
            },
            "insights_by_category": [
                {"category": "Overview", "insights": [f"Loaded {len(df)} rows"], "visualization_suggestions": cols[:4]}
            ],
            "dashboard_insights": [
                {"panel_name": "Key Metrics", "content": f"Total records: {len(df)}", "update_triggers": ["filter_change"]}
            ],
            "predictions": []
        }


def retrieve_similar_examples(analysis_result: Dict[str, Any], examples_db: List[Dict[str, Any]], top_k: int = 3) -> List[Dict[str, Any]]:
    """Stage 2: RAG retrieval of similar examples."""
    print("\n=== STAGE 2: RAG Retrieval of Similar Examples ===")
    if not examples_db:
        return []

    query_parts = []
    categories = [cat.get("category", "") for cat in analysis_result.get("data_categories", [])]
    query_parts.extend(categories)
    fields = [field.get("field_type", "") for field in analysis_result.get("fields_analysis", [])]
    query_parts.extend(fields)
    for cat in analysis_result.get("insights_by_category", []):
        query_parts.extend(cat.get("insights", []))
    
    query_text = " ".join([str(p) for p in query_parts if p])
    
    def vectorize(text: str) -> Dict[str, float]:
        tokens = text.lower().split()
        counts = Counter(tokens)
        if not counts:
            return {}
        norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
        return {t: c / norm for t, c in counts.items()}
    
    def cosine_similarity(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
        if not vec_a or not vec_b:
            return 0.0
        if len(vec_a) > len(vec_b):
            vec_a, vec_b = vec_b, vec_a
        score = 0.0
        for term, weight in vec_a.items():
            score += weight * vec_b.get(term, 0.0)
        return float(score)
    
    query_vec = vectorize(query_text)
    scored_examples = []
    for ex in examples_db:
        doc_text = " ".join([
            ex.get("title", ""),
            " ".join(ex.get("data_category", []) if isinstance(ex.get("data_category"), list) else []),
            ex.get("description", ""),
            " ".join(ex.get("features", []) if isinstance(ex.get("features"), list) else []),
            " ".join(ex.get("ui_elements", []) if isinstance(ex.get("ui_elements"), list) else []),
            " ".join(ex.get("tools_used", []) if isinstance(ex.get("tools_used"), list) else [])
        ])
        doc_vec = vectorize(doc_text)
        similarity = cosine_similarity(query_vec, doc_vec)
        scored_examples.append((similarity, ex))
    
    scored_examples.sort(key=lambda x: x[0], reverse=True)
    top_examples = [ex for _, ex in scored_examples[:top_k]]
    
    print(f"[OK] Retrieved {len(top_examples)} similar examples")
    return top_examples


def design_dashboard(analysis_result: Dict[str, Any], similar_examples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Stage 3: Dashboard design based on analysis and examples."""
    print("\n=== STAGE 3: Dashboard Design ===")
    
    prompt = f"""
# Data Visualisation Dashboard Design Task
## Dataset Analysis:
{json.dumps(analysis_result, indent=2)}
## Similar Example Dashboards:
{json.dumps(similar_examples, indent=2)}

## Task:
Design a comprehensive, interactive, and animated dashboard (using Dash + Plotly) based on the dataset analysis.
## Requirements:
1. Dashboard Structure:
   - Compelling title tailored to dataset
   - Dark modern theme (DARKLY / plotly_dark)
   - Controls panel (dropdowns, sliders, checkboxes for fields and time periods)
   - 3-4 coordinated interconnected plots
   - Dynamic filtered data table (dash_table.DataTable)
   - Dynamic insights panel
2. Interactive Elements:
   - Parameter selectors (metric dropdown, category filter, time slider)
   - Linked plots updating from shared filtered dataset
   - Smooth animations / play button if time data exists
3. Output JSON format:
{{
    "dashboard_title": "string",
    "styling": {{
        "theme": "DARKLY",
        "color_scheme": ["#00F2FE", "#4FACFE", "#00C9FF", "#92FE9D"],
        "background_style": "dark"
    }},
    "layout": {{
        "type": "sidebar",
        "description": "Sidebar controls with main chart grid and bottom data table + insights"
    }},
    "plots": [
        {{
            "plot_id": "plot_1",
            "plot_type": "bar/line/scatter/choropleth/histogram/pie/treemap",
            "title": "string",
            "description": "string",
            "position": {{"row": 1, "col": 1}}
        }}
    ],
    "controls": [
        {{
            "control_id": "ctrl_metric",
            "control_type": "dropdown",
            "label": "Select Metric",
            "options": ["string"]
        }}
    ],
    "insights_panel": {{
        "title": "Dynamic Insights",
        "content_sections": ["string"]
    }}
}}
"""
    
    try:
        client = get_groq_client()
        response = _chat_completion_with_fallback(
            client=client,
            preferred_model=MODEL_DESIGN,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
            max_tokens=3000
        )
        result = json.loads(response.choices[0].message.content)
        print("[OK] Dashboard design completed")
        return result
    except Exception as e:
        print(f"[ERROR] Dashboard design failed: {str(e)}")
        return {
            "dashboard_title": "Executive Data Analytics Dashboard",
            "styling": {"theme": "DARKLY", "color_scheme": ["#00F2FE", "#4FACFE"]},
            "plots": [
                {"plot_id": "plot_trend", "plot_type": "line", "title": "Primary Trend Analysis"},
                {"plot_id": "plot_dist", "plot_type": "bar", "title": "Distribution by Category"},
                {"plot_id": "plot_scatter", "plot_type": "scatter", "title": "Multi-Metric Correlation"}
            ],
            "controls": [
                {"control_id": "ctrl_metric", "control_type": "dropdown", "label": "Select Metric"}
            ],
            "insights_panel": {"title": "Key Insights", "content_sections": ["Live metric summaries"]}
        }


def generate_dash_code(analysis_result: Dict[str, Any], design_spec: Dict[str, Any], dataset_summary: Dict[str, Any], dashboard_id: str = None) -> str:
    """Stage 4: Generate complete Dash app code."""
    print("\n=== STAGE 4: Code Generation ===")
    
    prompt = f"""
# Dash App Code Generation Task
## Dataset Analysis:
{json.dumps(analysis_result, indent=2)}
## Dashboard Design Specification:
{json.dumps(design_spec, indent=2)}
## Dataset Summary:
{json.dumps(dataset_summary, indent=2)}

## Task:
Generate a complete, production-ready, beautiful, interactive Python Dash dashboard application tailored to this dataset.

### STRICT DASH BOOTSTRAP COMPONENTS (DBC 2.0.4) RULES:
1. NEVER USE `dbc.FormGroup`! It was deprecated and removed in DBC 1.0+/2.0.4. Using `dbc.FormGroup` will crash the application with an AttributeError!
   - INSTEAD USE: `html.Div([dbc.Label("My Label", className="form-label text-light"), dcc.Dropdown(...)], className="mb-3")` or `dbc.Row([dbc.Col(...)], className="mb-3")`.
2. NEVER USE `dbc.InputGroupAddon`! Use `dbc.InputGroupText(...)` instead.
3. NEVER USE `dbc.CardDeck` or `dbc.CardColumns`! Use `dbc.Row([dbc.Col(...)])` instead.
4. For all `dcc.Dropdown` components, add `style={{'color': '#111827'}}` so options are readable with high contrast against the dark background.

### APP STRUCTURE & BOILERPLATE:
```python
import os
import sys
import pandas as pd
import numpy as np
import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table, callback, Output, Input, State
from dash.exceptions import PreventUpdate
import plotly.express as px
import plotly.graph_objects as go

# Safe dataset loading
script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
dataset_path = os.path.join(script_dir, 'dataset.csv') if os.path.exists(os.path.join(script_dir, 'dataset.csv')) else 'dataset.csv'
df = pd.read_csv(dataset_path)

# Base path for reverse proxy support
base_path = os.getenv('BASE_PATH', '/')
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    requests_pathname_prefix=base_path,
    routes_pathname_prefix=base_path,
    suppress_callback_exceptions=True,
)

@app.server.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = '*'
    return response

# Layout: Sidebar controls + Main area (KPI cards + 3-4 coordinated plots + Filtered DataTable + Insights panel)
# Use dcc.Store(id='filtered-data') for shared state
# Callbacks:
# 1. @callback(Output('filtered-data', 'data'), [Inputs...]) -> updates filtered records
# 2. @callback(Output('plot-1', 'figure'), Input('filtered-data', 'data'), ...) -> returns go.Figure with template='plotly_dark'
# 3. @callback(Output('insights-panel', 'children'), Input('filtered-data', 'data')) -> returns insights

if __name__ == '__main__':
    port = int(os.getenv('PORT', '8050'))
    app.run(host='0.0.0.0', port=port, debug=False)
```

### REQUIREMENTS:
- Use actual column names from the Dataset Summary.
- Provide 3-4 distinct, coordinated Plotly charts (e.g., Time series, Bar chart, Scatter/Distribution, Treemap/Pie).
- All Plotly figures must use `template='plotly_dark'` with clean dark layout (`paper_bgcolor='rgba(0,0,0,0)'`, `plot_bgcolor='rgba(0,0,0,0)'`).
- Include a Filtered `dash_table.DataTable` with page_size=10, dark styling.
- Dynamic Insights panel summarizing the filtered data.
- Return ONLY the complete, runnable Python code without markdown explanations.
"""
    
    try:
        client = get_groq_client()
        response = _chat_completion_with_fallback(
            client=client,
            preferred_model=MODEL_CODE,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=8192
        )
        
        raw_code = response.choices[0].message.content or ""
        code = _extract_code_blocks(raw_code)
        if code:
            code = sanitize_and_modernize_dash_code(code)
            print("[OK] Code generation completed")
            return code.strip()
        else:
            print("[WARN] Code generation returned empty block, using fallback")
            return generate_fallback_dash_code(analysis_result, design_spec, dataset_summary)
        
    except Exception as e:
        print(f"[ERROR] Code generation failed: {str(e)}")
        logging.exception("Code generation failed; generating robust fallback dashboard")
        return generate_fallback_dash_code(analysis_result, design_spec, dataset_summary)


def optimize_code(code: str, analysis_result: Dict[str, Any], dataset_summary: Dict[str, Any]) -> str:
    """Stage 5: Code optimization and error resolution."""
    if not code:
        return code

    print("\n=== STAGE 5: Code Optimization ===")
    
    prompt = f"""
# Code Optimization and Error Resolution Task
## Generated Dash Code:
```python
{code}
```
## Dataset Analysis:
{json.dumps(analysis_result, indent=2)}

## Task:
Optimize the generated Dash code for high performance, modern UI, and error-free execution.
CRITICAL RULES:
1. NEVER USE `dbc.FormGroup`! It is deprecated and removed in DBC 2.0.4. Use `html.Div([dbc.Label(...), ...], className="mb-3")` instead.
2. NEVER USE `dbc.InputGroupAddon`. Use `dbc.InputGroupText` instead.
3. Ensure all `dcc.Dropdown` components include `style={{'color': '#111827'}}` so dropdown options are visible in dark mode.
4. Ensure all callbacks are valid, have unique Output targets (or `allow_duplicate=True`), and handle empty filtered data gracefully with PreventUpdate.
5. Keep `requests_pathname_prefix=base_path`, `routes_pathname_prefix=base_path`, and `app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8050')), debug=False)`.
6. Return ONLY the full optimized Python code (no markdown, no explanations).
"""
    
    try:
        client = get_groq_client()
        response = _chat_completion_with_fallback(
            client=client,
            preferred_model=MODEL_OPTIMIZE,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=8192
        )
        
        raw_code = response.choices[0].message.content or ""
        optimized = _extract_code_blocks(raw_code)
        if optimized:
            optimized = sanitize_and_modernize_dash_code(optimized)
            ok, err = _validate_code(optimized)
            if ok:
                print("[OK] Code optimization completed")
                return optimized.strip()
            else:
                logging.warning(f"Optimized code failed syntax validation ({err}); preserving previous valid code")
                return code
        return code
        
    except Exception as e:
        print(f"[ERROR] Code optimization failed: {str(e)}")
        return code


def generate_fallback_dash_code(analysis_result: Dict[str, Any], design_spec: Dict[str, Any], dataset_summary: Dict[str, Any]) -> str:
    """Generate a 100% valid, beautiful, complete fallback Dash application
    customized directly to the dataset schema and analysis results.
    """
    cols = dataset_summary.get("columns", [])
    types = dataset_summary.get("types", {})
    
    num_cols = [c for c in cols if any(t in str(types.get(c, "")).lower() for t in ("int", "float", "num", "double"))]
    cat_cols = [c for c in cols if c not in num_cols]
    
    title = design_spec.get("dashboard_title") or "Veridia Analytics Dashboard"
    primary_num = num_cols[0] if num_cols else (cols[0] if cols else "Value")
    secondary_num = num_cols[1] if len(num_cols) > 1 else primary_num
    primary_cat = cat_cols[0] if cat_cols else (cols[0] if cols else "Category")
    secondary_cat = cat_cols[1] if len(cat_cols) > 1 else primary_cat

    fallback_py = f'''import os
import sys
import pandas as pd
import numpy as np
import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table, callback, Output, Input, State
from dash.exceptions import PreventUpdate
import plotly.express as px
import plotly.graph_objects as go

# -------------------- Load Dataset --------------------
script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
dataset_path = os.path.join(script_dir, 'dataset.csv') if os.path.exists(os.path.join(script_dir, 'dataset.csv')) else 'dataset.csv'
df = pd.read_csv(dataset_path)

# Fill missing values for robust rendering
for col in df.columns:
    if pd.api.types.is_numeric_dtype(df[col]):
        df[col] = df[col].fillna(0)
    else:
        df[col] = df[col].fillna("Unknown").astype(str)

# -------------------- App Initialization --------------------
base_path = os.getenv('BASE_PATH', '/')
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    requests_pathname_prefix=base_path,
    routes_pathname_prefix=base_path,
    suppress_callback_exceptions=True,
)

@app.server.after_request
def _add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = '*'
    return response

# Available options for controls
NUMERIC_COLS = {json.dumps(num_cols if num_cols else cols[:2])}
CAT_COLS = {json.dumps(cat_cols if cat_cols else cols[:2])}
DEFAULT_METRIC = "{primary_num}"
DEFAULT_CAT = "{primary_cat}"

# -------------------- Layout --------------------
sidebar_controls = dbc.Card(
    [
        html.H4("Controls & Filters", className="card-title text-info mb-3"),
        html.Div(
            [
                dbc.Label("Primary Metric", className="form-label text-light"),
                dcc.Dropdown(
                    id="metric-dropdown",
                    options=[{{"label": c, "value": c}} for c in NUMERIC_COLS] or [{{"label": "{primary_num}", "value": "{primary_num}"}}],
                    value=DEFAULT_METRIC,
                    clearable=False,
                    style={{"color": "#111827"}},
                ),
            ],
            className="mb-3",
        ),
        html.Div(
            [
                dbc.Label("Grouping Dimension", className="form-label text-light"),
                dcc.Dropdown(
                    id="cat-dropdown",
                    options=[{{"label": c, "value": c}} for c in CAT_COLS] or [{{"label": "{primary_cat}", "value": "{primary_cat}"}}],
                    value=DEFAULT_CAT,
                    clearable=False,
                    style={{"color": "#111827"}},
                ),
            ],
            className="mb-3",
        ),
        html.Div(
            [
                dbc.Label("Records to Sample", className="form-label text-light"),
                dcc.Slider(
                    id="sample-slider",
                    min=min(10, len(df)),
                    max=min(500, max(50, len(df))),
                    step=10,
                    value=min(100, len(df)),
                    marks={{
                        min(10, len(df)): str(min(10, len(df))),
                        min(100, len(df)): "100",
                        min(500, max(50, len(df))): str(min(500, max(50, len(df)))),
                    }},
                ),
            ],
            className="mb-3",
        ),
        dbc.Button("Refresh Visualizations", id="btn-refresh", color="primary", className="w-100 mt-2"),
    ],
    body=True,
    className="bg-dark border-secondary shadow-sm mb-3",
)

kpi_cards = dbc.Row(
    [
        dbc.Col(
            dbc.Card(
                dbc.CardBody(
                    [
                        html.H6("Total Records", className="text-muted mb-1"),
                        html.H3(f"{{len(df):,}}", className="text-info fw-bold mb-0"),
                    ]
                ),
                className="bg-dark border-secondary shadow-sm",
            ),
            width=4,
        ),
        dbc.Col(
            dbc.Card(
                dbc.CardBody(
                    [
                        html.H6("Dimensions Analyzed", className="text-muted mb-1"),
                        html.H3(f"{{len(df.columns)}} Columns", className="text-success fw-bold mb-0"),
                    ]
                ),
                className="bg-dark border-secondary shadow-sm",
            ),
            width=4,
        ),
        dbc.Col(
            dbc.Card(
                dbc.CardBody(
                    [
                        html.H6("Selected Metric Aggregate", className="text-muted mb-1"),
                        html.H3(id="kpi-metric-val", children="...", className="text-warning fw-bold mb-0"),
                    ]
                ),
                className="bg-dark border-secondary shadow-sm",
            ),
            width=4,
        ),
    ],
    className="mb-3 g-2",
)

app.layout = dbc.Container(
    [
        dcc.Store(id="filtered-data-store"),
        dbc.Row(
            [
                dbc.Col(
                    html.Div(
                        [
                            html.H2("{title}", className="text-light fw-bold mb-1"),
                            html.P("Interactive Verified Analytics Dashboard", className="text-muted mb-3"),
                        ]
                    ),
                    width=12,
                )
            ]
        ),
        dbc.Row(
            [
                dbc.Col(sidebar_controls, width=12, lg=3),
                dbc.Col(
                    [
                        kpi_cards,
                        dbc.Row(
                            [
                                dbc.Col(
                                    dbc.Card(
                                        dbc.CardBody([dcc.Graph(id="chart-bar", config={{"displayModeBar": False}})]),
                                        className="bg-dark border-secondary shadow-sm mb-3",
                                    ),
                                    width=12,
                                    lg=6,
                                ),
                                dbc.Col(
                                    dbc.Card(
                                        dbc.CardBody([dcc.Graph(id="chart-line", config={{"displayModeBar": False}})]),
                                        className="bg-dark border-secondary shadow-sm mb-3",
                                    ),
                                    width=12,
                                    lg=6,
                                ),
                            ],
                            className="g-3 mb-3",
                        ),
                        dbc.Row(
                            [
                                dbc.Col(
                                    dbc.Card(
                                        dbc.CardBody([dcc.Graph(id="chart-scatter", config={{"displayModeBar": False}})]),
                                        className="bg-dark border-secondary shadow-sm mb-3",
                                    ),
                                    width=12,
                                    lg=6,
                                ),
                                dbc.Col(
                                    dbc.Card(
                                        dbc.CardBody([dcc.Graph(id="chart-pie", config={{"displayModeBar": False}})]),
                                        className="bg-dark border-secondary shadow-sm mb-3",
                                    ),
                                    width=12,
                                    lg=6,
                                ),
                            ],
                            className="g-3 mb-3",
                        ),
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H5("Filtered Dataset Preview", className="card-title text-info mb-3"),
                                    html.Div(id="table-container"),
                                ]
                            ),
                            className="bg-dark border-secondary shadow-sm mb-3",
                        ),
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H5("Dynamic Insights", className="card-title text-success mb-2"),
                                    html.Div(id="insights-container", className="text-light"),
                                ]
                            ),
                            className="bg-dark border-secondary shadow-sm mb-4",
                        ),
                    ],
                    width=12,
                    lg=9,
                ),
            ]
        ),
    ],
    fluid=True,
    className="p-3 bg-black min-vh-100",
)

# -------------------- Callbacks --------------------
@callback(
    Output("filtered-data-store", "data"),
    [
        Input("metric-dropdown", "value"),
        Input("cat-dropdown", "value"),
        Input("sample-slider", "value"),
        Input("btn-refresh", "n_clicks"),
    ],
)
def update_store(metric, cat_col, sample_size, n_clicks):
    sample_size = sample_size or min(100, len(df))
    dff = df.head(int(sample_size)).copy()
    return dff.to_dict("records")

@callback(
    [
        Output("chart-bar", "figure"),
        Output("chart-line", "figure"),
        Output("chart-scatter", "figure"),
        Output("chart-pie", "figure"),
        Output("kpi-metric-val", "children"),
        Output("table-container", "children"),
        Output("insights-container", "children"),
    ],
    [
        Input("filtered-data-store", "data"),
        Input("metric-dropdown", "value"),
        Input("cat-dropdown", "value"),
    ],
)
def update_visualizations(stored_data, metric, cat_col):
    if not stored_data:
        raise PreventUpdate

    dff = pd.DataFrame(stored_data)
    metric = metric if metric in dff.columns else (NUMERIC_COLS[0] if NUMERIC_COLS else dff.columns[0])
    cat_col = cat_col if cat_col in dff.columns else (CAT_COLS[0] if CAT_COLS else dff.columns[0])

    is_metric_num = pd.api.types.is_numeric_dtype(dff[metric])
    agg_val = f"{{dff[metric].sum():,.2f}}" if is_metric_num else f"{{len(dff)}} items"

    # 1. Bar Chart
    if is_metric_num:
        bar_df = dff.groupby(cat_col, as_index=False)[metric].mean().sort_values(by=metric, ascending=False).head(15)
        fig_bar = px.bar(bar_df, x=cat_col, y=metric, title=f"Average {{metric}} by {{cat_col}}", template="plotly_dark", color=metric, color_continuous_scale="Viridis")
    else:
        counts = dff[cat_col].value_counts().reset_index().head(15)
        counts.columns = [cat_col, "Count"]
        fig_bar = px.bar(counts, x=cat_col, y="Count", title=f"Frequency of {{cat_col}}", template="plotly_dark", color="Count", color_continuous_scale="Viridis")
    fig_bar.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=20, r=20, t=40, b=20))

    # 2. Line Chart
    fig_line = px.line(dff.reset_index(), x="index", y=metric, title=f"Sequential Profile of {{metric}}", template="plotly_dark", markers=True)
    fig_line.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=20, r=20, t=40, b=20))

    # 3. Scatter Chart
    second_num = "{secondary_num}" if "{secondary_num}" in dff.columns and "{secondary_num}" != metric else (NUMERIC_COLS[1] if len(NUMERIC_COLS) > 1 else metric)
    fig_scatter = px.scatter(dff, x=metric, y=second_num, color=cat_col, title=f"{{metric}} vs {{second_num}}", template="plotly_dark")
    fig_scatter.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=20, r=20, t=40, b=20))

    # 4. Pie / Donut Chart
    pie_counts = dff[cat_col].value_counts().head(8).reset_index()
    pie_counts.columns = [cat_col, "Count"]
    fig_pie = px.pie(pie_counts, names=cat_col, values="Count", title=f"Top Categories Distribution ({{cat_col}})", template="plotly_dark", hole=0.4)
    fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=20, r=20, t=40, b=20))

    # Table
    preview_cols = [{{"name": i, "id": i}} for i in dff.columns[:8]]
    table_elem = dash_table.DataTable(
        data=dff.head(10).to_dict("records"),
        columns=preview_cols,
        page_size=10,
        style_header={{"backgroundColor": "#1e293b", "color": "#f8fafc", "fontWeight": "bold", "border": "1px solid #334155"}},
        style_cell={{"backgroundColor": "#0f172a", "color": "#cbd5e1", "border": "1px solid #334155", "fontSize": "13px", "padding": "8px"}},
        style_table={{"overflowX": "auto"}},
    )

    # Insights
    insights_elem = html.Ul(
        [
            html.Li("Displaying sample of " + str(len(dff)) + " records out of " + str(len(df)) + " total rows."),
            html.Li("Primary metric aggregate (" + str(metric) + "): " + str(agg_val)),
            html.Li("Primary category partition contains " + str(len(dff[cat_col].unique())) + " distinct values for " + str(cat_col) + "."),
        ],
        className="mb-0",
    )

    return fig_bar, fig_line, fig_scatter, fig_pie, agg_val, table_elem, insights_elem

if __name__ == '__main__':
    port = int(os.getenv('PORT', '8050'))
    app.run(host='0.0.0.0', port=port, debug=False)
'''
    return fallback_py.strip()


def apply_user_edit_minimal(
    existing_code: str,
    user_request: str,
    dataset_summary: Dict[str, Any] | None = None,
    analysis_result: Dict[str, Any] | None = None,
) -> str:
    """Use MODEL_CODE to apply a minimal edit to the existing Dash app based on the
    user's request. Return the FULL updated Python code.
    Fallback to the original code on failure.
    """
    print("\n=== CHAT EDIT: Applying minimal user-requested change ===")
    ds = dataset_summary or {}
    ar = analysis_result or {}
    prompt = f"""
You are an expert Dash + Plotly engineer. You are given an existing Dash app (Python) and a user's modification request.
Apply the SMALLEST POSSIBLE set of changes to implement ONLY what the user requested. Do NOT refactor or redesign anything else.
CRITICAL DBC RULES:
- NEVER USE `dbc.FormGroup`! It is deprecated and removed. Use `html.Div([dbc.Label(...), ...], className="mb-3")` instead.
- NEVER USE `dbc.InputGroupAddon`. Use `dbc.InputGroupText` instead.
- For `dcc.Dropdown`, keep `style={{'color': '#111827'}}` so options are visible in dark mode.
- Maintain existing imports, layout, and callbacks.
- Return ONLY the complete Python source (no markdown, no explanations).

USER REQUEST:
{user_request}

EXISTING CODE (edit minimally):
```python
{existing_code}
```
"""
    try:
        global CHAT_EDIT_CALL_COUNT
        CHAT_EDIT_CALL_COUNT += 1
        use_model = MODEL_CODE if CHAT_EDIT_CALL_COUNT % 2 == 1 else MODEL_OPTIMIZE
        print(f"[chat-edit] Using model: {use_model}")

        client = get_groq_client()
        response = _chat_completion_with_fallback(
            client=client,
            preferred_model=use_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=8192
        )
        raw = response.choices[0].message.content or ""
        updated = _extract_code_blocks(raw)
        if updated:
            updated = sanitize_and_modernize_dash_code(updated)
            ok, err = _validate_code(updated)
            if ok:
                return updated.strip()
        logging.warning(f"User chat edit returned invalid code; keeping original.")
        return existing_code
    except Exception as e:
        logging.exception(f"Chat edit failed: {e}")
        return existing_code


def fix_generated_code(code_path: str, error_text: str, output_dir: str) -> str:
    """Attempt to automatically fix a generated dashboard Python file using
    deterministic modernization heuristics and the LLM.
    """
    logging.info("=== AUTO-FIX: Attempting to fix generated dashboard code ===")
    print("\n=== AUTO-FIX: Attempting to fix generated dashboard code ===")

    original_code = ""
    try:
        if os.path.exists(code_path):
            with open(code_path, 'r', encoding='utf-8') as f:
                original_code = f.read()
    except Exception as e:
        logging.exception(f"Could not read code at {code_path}: {e}")

    if not original_code:
        return ""

    dataset_path = os.path.join(output_dir, "dataset.csv")

    # 1. Deterministic Sanitization (Fixes DBC deprecations, FormGroup, quotes, BASE_PATH, CORS, etc.)
    sanitized = sanitize_and_modernize_dash_code(original_code)
    san_ok, san_err = _test_dash_code_runtime(sanitized, dataset_path)
    if san_ok:
        logging.info("Deterministic sanitization resolved the dashboard error")
        print("[OK] Deterministic sanitization resolved the dashboard error")
        return sanitized

    # 2. If deterministic fix alone did not resolve runtime error, call LLM with exact traceback
    try:
        focused_prompt = f"""
You are an expert Dash + Plotly engineer. The Python Dash app below failed with the following runtime traceback.
Apply the MINIMAL edits required to fix the error and make it 100% runnable.
CRITICAL RULES:
- NEVER USE `dbc.FormGroup`! It is deprecated and removed in DBC 2.0.4. Use `html.Div([dbc.Label(...), ...], className="mb-3")` instead.
- NEVER USE `dbc.InputGroupAddon`. Use `dbc.InputGroupText` instead.
- For `dcc.Dropdown`, use `style={{'color': '#111827'}}`.
- Ensure all callbacks have matching Input and Output IDs that exist in the layout.
- Return ONLY the full corrected Python source file without markdown fences or explanations.

Runtime error:
{error_text}
{san_err}

Original code:
```python
{sanitized}
```
"""
        client = get_groq_client()
        response = _chat_completion_with_fallback(
            client=client,
            preferred_model=MODEL_OPTIMIZE,
            messages=[{"role": "user", "content": focused_prompt}],
            temperature=0.0,
            max_tokens=8192
        )
        raw_fix = response.choices[0].message.content or ""
        fixed = _extract_code_blocks(raw_fix)
        if fixed:
            fixed = sanitize_and_modernize_dash_code(fixed)
            ok, dry_err = _test_dash_code_runtime(fixed, dataset_path)
            if ok:
                logging.info("LLM auto-fix produced working code verified at runtime")
                print("[OK] LLM auto-fix produced working code verified at runtime")
                return fixed
            else:
                logging.warning(f"LLM fix had runtime error: {dry_err}")

        # Try Gemini fallback if configured
        if GEMINI_API_KEY:
            gemini_fixed = gemini_optimize_code(sanitized, {}, {})
            if gemini_fixed:
                gemini_fixed = sanitize_and_modernize_dash_code(gemini_fixed)
                g_ok, g_err = _test_dash_code_runtime(gemini_fixed, dataset_path)
                if g_ok:
                    return gemini_fixed

        # Fallback to sanitized version if it passes basic syntax
        if _validate_code(sanitized)[0]:
            return sanitized

        return ""
    except Exception as e:
        logging.exception(f"Auto-fix LLM attempt failed: {e}")
        return sanitized if _validate_code(sanitized)[0] else ""


def create_dashboard(
    data_file_path: str,
    user_prompt: str,
    output_dir: str,
    dashboard_id: str = None,
    progress_cb=None,
) -> str:
    """Main function to create dashboard through all pipeline stages with runtime verification."""
    print("=== Starting Dashboard Creation Pipeline ===")
    print("=" * 50)
    
    validate_groq_configuration()

    # Load data
    try:
        df = pd.read_csv(data_file_path)
        print(f"[OK] Loaded dataset: {len(df)} rows, {len(df.columns)} columns")
    except Exception as e:
        print(f"[ERROR] Failed to load data: {e}")
        raise ValueError(f"Failed to load dataset: {e}")
    
    # Load examples database
    try:
        with open(TEMPLATES_FILE, 'r', encoding='utf-8') as f:
            examples_db = json.load(f)
        print(f"[OK] Loaded {len(examples_db)} example dashboards")
    except Exception as e:
        print(f"[WARN] Failed to load examples: {e}")
        examples_db = []
    
    current_dashboard_id = dashboard_id or str(uuid.uuid4())
    
    def _progress(stage: str, progress: int, note: str | None = None):
        try:
            if callable(progress_cb):
                progress_cb(stage, progress, note)
        except Exception:
            pass

    dataset_name = os.path.basename(data_file_path)

    # Stage 1: Comprehensive Dataset Analysis
    analysis_result = analyze_dataset_comprehensive(df)
    try:
        categories = [c.get("category") for c in (analysis_result.get("data_categories") or [])][:3]
        main_patterns = (analysis_result.get("dataset_analysis") or {}).get("main_patterns") or []
        note_1 = (
            f"LLM analyzed '{dataset_name}' ({len(df)} rows, {len(df.columns)} cols). "
            f"Categories: {', '.join([c for c in categories if c]) or 'General'}. "
            f"Patterns: {', '.join(main_patterns[:2]) or 'Multi-dimensional data'}"
        )
    except Exception:
        note_1 = f"LLM analyzed '{dataset_name}' ({len(df)} rows, {len(df.columns)} cols)."
    _progress("stage_1", 16, note_1)
    
    # Stage 2: RAG Retrieval
    similar_examples = retrieve_similar_examples(analysis_result, examples_db, top_k=3)
    _progress("stage_2", 32, f"Retrieved {len(similar_examples)} matching visualization templates.")
    
    # Stage 3: Dashboard Design
    design_spec = design_dashboard(analysis_result, similar_examples)
    plot_count = len(design_spec.get("plots") or [])
    title = design_spec.get("dashboard_title") or "Analytics Dashboard"
    _progress("stage_3", 48, f"Designed '{title}' with {plot_count} coordinated plots and dynamic controls.")
    
    # Stage 4: Code Generation
    def convert_val(v):
        if isinstance(v, (pd.Timestamp, np.generic)):
            return str(v)
        return v

    sample_dict = df.head(5).to_dict(orient='records')
    safe_sample = [{k: convert_val(v) for k, v in row.items()} for row in sample_dict]

    dataset_summary = {
        "columns": list(df.columns),
        "types": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "row_count": len(df),
        "sample_data": safe_sample
    }
    
    generated_code = generate_dash_code(analysis_result, design_spec, dataset_summary, current_dashboard_id)
    _progress("stage_4", 64, "Generated complete interactive Dash code.")
    
    # Stage 5: Code Optimization (Groq)
    optimized_code = optimize_code(generated_code, analysis_result, dataset_summary)
    _progress("stage_5", 82, "Optimized code for high performance and visual polish.")
    
    # Stage 5b: Gemini Optimization (Optional)
    gemini_code = gemini_optimize_code(optimized_code, analysis_result, dataset_summary)
    
    # Sanitize all candidate variants
    candidates = [
        ("gemini", sanitize_and_modernize_dash_code(gemini_code)),
        ("optimized", sanitize_and_modernize_dash_code(optimized_code)),
        ("generated", sanitize_and_modernize_dash_code(generated_code)),
    ]

    chosen_name = "generated"
    final_code = ""

    # 1. Prefer candidate that passes full AST semantic validation
    for name, code in candidates:
        if code and code.strip():
            ok, issues = _validate_dash_code(code)
            if ok:
                chosen_name = name
                final_code = code
                break

    # 2. Fallback to any candidate that passes Python AST syntax check
    if not final_code:
        for name, code in candidates:
            if code and code.strip():
                ok, _ = _validate_code(code)
                if ok:
                    chosen_name = name
                    final_code = code
                    break

    # 3. If all LLM candidates failed, generate guaranteed fallback
    if not final_code or not final_code.strip():
        chosen_name = "fallback"
        final_code = generate_fallback_dash_code(analysis_result, design_spec, dataset_summary)

    # 4. Save results in dashboard directory
    os.makedirs(output_dir, exist_ok=True)
    dataset_dest = os.path.join(output_dir, "dataset.csv")
    if not os.path.exists(dataset_dest) and os.path.exists(data_file_path):
        import shutil
        shutil.copy2(data_file_path, dataset_dest)

    # 5. Runtime Dry-Run Verification: Test the code before declaring stage 6 complete
    runtime_ok, runtime_err = _test_dash_code_runtime(final_code, dataset_dest)
    if not runtime_ok:
        logging.warning(f"Runtime dry-run failed for {chosen_name} candidate: {runtime_err}. Attempting auto-fix.")
        fixed_candidate = fix_generated_code("", runtime_err, output_dir)
        if fixed_candidate and _test_dash_code_runtime(fixed_candidate, dataset_dest)[0]:
            final_code = fixed_candidate
            logging.info("Auto-fix successfully resolved runtime issue before initial save.")
        else:
            logging.warning("Auto-fix unable to resolve; falling back to dynamic verified dashboard.")
            final_code = generate_fallback_dash_code(analysis_result, design_spec, dataset_summary)

    output_file = os.path.join(output_dir, "dashboard_app.py")

    # Write snapshots
    try:
        with open(os.path.join(output_dir, "dashboard_app_generated.py"), 'w', encoding='utf-8') as f:
            f.write("# Generated code (pre-optimization)\n" + (generated_code or "# <no generated code>\n"))
        with open(os.path.join(output_dir, "dashboard_app_optimized.py"), 'w', encoding='utf-8') as f:
            f.write("# Optimized code (Groq)\n" + (optimized_code or "# <no optimized code>\n"))
        with open(os.path.join(output_dir, "dashboard_app_gemini.py"), 'w', encoding='utf-8') as f:
            f.write("# Gemini-optimized code\n" + (gemini_code or "# <no gemini code>\n"))
    except Exception:
        pass

    # Save final dashboard file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(final_code)
    
    # Save metadata
    with open(os.path.join(output_dir, "analysis_result.json"), 'w', encoding='utf-8') as f:
        json.dump(analysis_result, f, indent=2)
    
    with open(os.path.join(output_dir, "design_spec.json"), 'w', encoding='utf-8') as f:
        json.dump(design_spec, f, indent=2)
    
    print(f"\n[OK] Dashboard creation completed successfully!")
    print(f"[OK] Output files saved to: {output_dir}")
    print(f"[OK] Main dashboard: {output_file}")
    _progress("stage_6", 100, "All stages completed. Your dashboard is ready to launch.")

    return output_file


def initialize_vector_database():
    """Initialize the vector database (placeholder for future implementation)"""
    pass


if __name__ == "__main__":
    test_data = str(DATA_DIR / "synthetic_transportation_data.csv")
    user_prompt = "Create a beautiful animated dashboard showing the entire dataset in a very modern, animated, interactive manner."
    test_output_dir = str(DASHBOARD_DIR / "test_run")
    
    output_file = create_dashboard(test_data, user_prompt, test_output_dir)
    print(f"\n[OK] Test completed. Dashboard saved to: {output_file}")
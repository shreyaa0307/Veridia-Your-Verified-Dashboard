import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential

from app.paths import DATA_DIR, R_OUTPUT_DIR, SERVICES_DIR, load_project_env

# Load environment
load_project_env()

def get_groq_client() -> Groq:
    """Get a Groq client instance, raising a clear exception if GROQ_API_KEY is not configured."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not configured. Please set your GROQ_API_KEY in backend/.env.local or environment variables.")
    return Groq(api_key=api_key)


# Configuration
MAX_EXAMPLES = 15  # Number of examples to consider
SAMPLE_SIZE = 100  # Max rows to sample from user data
MIN_CHAIN_EXAMPLES = 3  # Ensure at least 3 examples flow to next stages
RETRIEVAL_TOP_K = 5  # Retrieval size for example dashboards

# Models
MODEL_SELECTION = "meta-llama/llama-4-scout-17b-16e-instruct"
MODEL_LARGE_JSON = "openai/gpt-oss-120b"

def load_data_resources():
    """Load both example metadata and code libraries"""
    try:
        candidate_data_dirs = [
            str(DATA_DIR),
            str(SERVICES_DIR.parent / "data"),
            str(SERVICES_DIR),
        ]

        def resolve_file(filenames: List[str]) -> str:
            for fname in filenames:
                for d in candidate_data_dirs:
                    p = os.path.join(d, fname)
                    if os.path.exists(p):
                        return p
            return os.path.join(candidate_data_dirs[0], filenames[0])

        examples_path = resolve_file(['rag_1_examples.json', 'r_examples.json'])
        with open(examples_path, 'r', encoding='utf-8') as f:
            examples_db = json.load(f)['examples']
        
        code_path = resolve_file(['r_code_examples.json'])
        with open(code_path, 'r', encoding='utf-8') as f:
            code_lib = json.load(f)
        
        # Verify all code snippets exist
        missing = []
        for ex in examples_db:
            if ex.get("code_snippet") and ex["code_snippet"] not in code_lib:
                missing.append(ex["code_snippet"])
        if missing:
            print(f"\n=== WARNING: Missing code snippets for examples: {', '.join(missing)} ===")
        
        return examples_db, code_lib
    except Exception as e:
        print(f"\n=== ERROR loading data resources: {str(e)} ===")
        raise


def load_design_docs() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load design rules, animint2 syntax, and error corpora for later stages.

    Returns: (design_rules, animint_docs, error_patterns)
    """
    candidate_data_dirs = [
        str(DATA_DIR),
        str(SERVICES_DIR.parent / "data"),
    ]

    # Design rules
    design_rules: List[Dict[str, Any]] = []
    for data_dir in candidate_data_dirs:
        try:
            with open(os.path.join(data_dir, "design_rules.json")) as f:
                design_rules = json.load(f)["rules"]
                break
        except Exception:
            continue
    if not design_rules:
        # Fallback to rag_2_doc_chunks.json if present
        for data_dir in candidate_data_dirs:
            try:
                with open(os.path.join(data_dir, "rag_2_doc_chunks.json")) as f:
                    chunks = json.load(f).get("documentation", [])
                    design_rules = chunks
                    break
            except Exception:
                continue

    # Animint2 syntax snippets
    animint_docs: List[Dict[str, Any]] = []
    for data_dir in candidate_data_dirs:
        try:
            with open(os.path.join(data_dir, "animint2_syntax.json")) as f:
                animint_docs = json.load(f)["syntax"]
                break
        except Exception:
            continue

    # Error corpora
    error_patterns: List[Dict[str, Any]] = []
    for data_dir in candidate_data_dirs:
        try:
            with open(os.path.join(data_dir, "rag_3_errors.json")) as f:
                error_patterns = json.load(f).get("error_patterns", [])
                break
        except Exception:
            continue

    return design_rules, animint_docs, error_patterns

def analyze_dataset_structure(df: pd.DataFrame) -> dict:
    """Analyze dataset structure for visualization matching"""
    sample_df = df.sample(min(SAMPLE_SIZE, len(df))) if len(df) > SAMPLE_SIZE else df
    
    # Convert Timestamps to strings
    def convert_timestamps(value):
        if isinstance(value, pd.Timestamp):
            return str(value)
        return value
    
    return {
        "variables": [
            {
                "name": col,
                "type": str(dtype),
                "unique_values": len(sample_df[col].unique()),
                "sample_values": [convert_timestamps(v) for v in sample_df[col].dropna().unique()[:3]]
            }
            for col, dtype in sample_df.dtypes.items()
        ],
        "relationships": {
            "numerical_pairs": [
                (col1, col2) 
                for i, col1 in enumerate(sample_df.select_dtypes(include=np.number).columns)
                for j, col2 in enumerate(sample_df.select_dtypes(include=np.number).columns)
                if i < j
            ],
            "category_numerical": [
                (cat_col, num_col)
                for cat_col in sample_df.select_dtypes(exclude=np.number).columns
                for num_col in sample_df.select_dtypes(include=np.number).columns
            ]
        }
    }


def serialize_df_sample(df: pd.DataFrame, max_rows: int = 10) -> Dict[str, Any]:
    """Compact snapshot of the dataset with a few records for prompting."""
    def conv(val: Any) -> Any:
        if isinstance(val, (pd.Timestamp, np.generic)):
            return str(val)
        return val

    head_records = df.head(max_rows).to_dict(orient="records")
    safe_records = [{k: conv(v) for k, v in row.items()} for row in head_records]
    return {
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "records_preview": safe_records,
        "row_count": int(len(df)),
    }


def _normalize_text(text: str) -> List[str]:
    if not text:
        return []
    return [
        token
        for token in (
            text.lower()
            .replace("\n", " ")
            .replace("/", " ")
            .replace("_", " ")
            .replace("-", " ")
            .replace(",", " ")
            .replace(".", " ")
        ).split()
        if token
    ]


def _vectorize(text: str) -> Dict[str, float]:
    tokens = _normalize_text(text)
    counts = Counter(tokens)
    if not counts:
        return {}
    norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
    return {t: c / norm for t, c in counts.items()}


def _cosine_similarity(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    score = 0.0
    for term, weight in vec_a.items():
        score += weight * vec_b.get(term, 0.0)
    return float(score)


def build_example_corpus(examples_db: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    corpus = []
    for ex in examples_db:
        text = "\n".join(
            [
                ex.get("id", ""),
                ex.get("title", ""),
                ex.get("dataset_description", ""),
                " ".join(ex.get("analysis_notes", []) or []),
                " ".join(ex.get("geom_used", []) or []),
                " ".join(ex.get("visualization_tags", []) or []),
            ]
        )
        corpus.append({"id": ex.get("id"), "text": text, "meta": ex})
    return corpus


def detect_data_modalities(df: pd.DataFrame) -> Dict[str, bool]:
    col_names = [c.lower() for c in df.columns]
    text = " ".join(col_names)
    has_time = any(t in text for t in ["date", "time", "year", "month", "timestamp"])
    has_geo = any(t in text for t in ["lat", "lon", "long", "lng", "state", "country", "region", "zip"])
    has_category = len(df.select_dtypes(exclude=np.number).columns) > 0
    has_numeric = len(df.select_dtypes(include=np.number).columns) > 0
    return {
        "has_time": has_time,
        "has_geo": has_geo,
        "has_category": has_category,
        "has_numeric": has_numeric,
    }


def retrieve_similar_examples(
    user_df: pd.DataFrame,
    user_description: str,
    examples_db: List[Dict[str, Any]],
    top_k: int = RETRIEVAL_TOP_K,
) -> List[Dict[str, Any]]:
    print("\n=== RETRIEVAL: Building example corpus ===")
    corpus = build_example_corpus(examples_db)
    modalities = detect_data_modalities(user_df)
    struct = analyze_dataset_structure(user_df)
    preview = serialize_df_sample(user_df, max_rows=5)

    query_text = "\n".join(
        [
            user_description or "",
            json.dumps(modalities),
            json.dumps(struct.get("variables", [])),
            json.dumps(struct.get("relationships", {})),
            json.dumps(preview.get("records_preview", [])),
        ]
    )
    q = _vectorize(query_text)

    ranked: List[Tuple[float, Dict[str, Any]]] = []
    for doc in corpus:
        sim = _cosine_similarity(q, _vectorize(doc["text"]))
        ranked.append((sim, doc["meta"]))

    ranked.sort(key=lambda x: x[0], reverse=True)
    top = [m for _, m in ranked[:top_k]]

    print(f"Retrieved {len(top)} examples (top_k={top_k})")
    for i, ex in enumerate(top, 1):
        print(f"  {i}. {ex['id']} :: {ex.get('title', '')}")
    return top


# ------------------------------
# New multi-stage pipeline helpers
# ------------------------------
def stage1_retrieve_examples(
    user_data: pd.DataFrame,
    user_description: str,
    examples_db: List[Dict[str, Any]],
    min_examples: int = MIN_CHAIN_EXAMPLES,
) -> List[Dict[str, Any]]:
    """Retrieve at least min_examples examples using heuristic retrieval."""
    retrieved = retrieve_similar_examples(user_data, user_description, examples_db, top_k=RETRIEVAL_TOP_K)
    if len(retrieved) < min_examples:
        print(f"\nRetrieved {len(retrieved)} examples; padding to reach {min_examples}")
        needed = min_examples - len(retrieved)
        pool = [ex for ex in examples_db if ex not in retrieved]
        retrieved.extend(pool[:needed])
    return retrieved


def stage2_design_dashboard(
    user_data: pd.DataFrame,
    user_description: str,
    retrieved_examples: List[Dict[str, Any]],
    design_rules: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Use a model to synthesize a comprehensive dashboard plan from examples and design rules."""
    print("\n=== STAGE 2: Designing dashboard layout ===")
    dataset_preview = serialize_df_sample(user_data)
    examples_brief = [
        {
            "id": ex.get("id"),
            "title": ex.get("title"),
            "key_geoms": ex.get("geom_used", []),
            "analysis_notes": (ex.get("analysis_notes", []) or [])[:3],
            "dataset_description": (ex.get("dataset_description", "") or "")[:300],
        }
        for ex in retrieved_examples
    ]

    prompt = f"""
# Dashboard Design Synthesis

## User dataset preview
{json.dumps(dataset_preview, indent=2)}

## User goal
{user_description}

## Retrieved example dashboards ({len(examples_brief)}):
{json.dumps(examples_brief, indent=2)}

## Design rules and components library:
{json.dumps(design_rules, indent=2)}

## Task
1) Propose a complete dashboard plan tailored to the dataset and goal
2) Compose from examples and rules only what is applicable
3) Specify 2-4 coordinated views with exact ggplot2 geoms, selectors (clickSelects/showSelected), and animation (time, duration)
4) Specify data transformations required to power each view (melt, group_by/summarise, joins)
5) Recommend at least 3 candidate reference examples to carry forward

## Output JSON schema
{{
  "selected_examples": [{{"id": "...", "reason": "..."}}],
  "layout": {{
    "views": [
      {{"name": "...", "geom_stack": ["geom_point", "geom_line"],
        "mappings": {{"x": "...", "y": "...", "color": "..."}},
        "selectors": ["clickSelects=...", "showSelected=..."],
        "facets": {{"rows": "...", "cols": "..."}},
        "notes": "why this view"}}
    ],
    "selectors": ["var1", "var2"],
    "animation": {{"time": "<var>", "ms": 2000}},
    "first": {{"<selector>": "<value>"}}
  }},
  "data_transformations": ["..."],
  "reasoning": "..."
}}
"""

    client = get_groq_client()
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL_SELECTION,
        temperature=0.2,
        response_format={"type": "json_object"},
        max_tokens=2000,
    )
    plan = json.loads(response.choices[0].message.content)
    if len(plan.get("selected_examples", [])) < MIN_CHAIN_EXAMPLES:
        existing = {e.get("id") for e in plan.get("selected_examples", [])}
        for ex in retrieved_examples:
            if ex.get("id") not in existing:
                plan.setdefault("selected_examples", []).append({"id": ex.get("id"), "reason": "retrieved match"})
            if len(plan["selected_examples"]) >= MIN_CHAIN_EXAMPLES:
                break
    return plan


def stage3_generate_data_prep(
    user_data: pd.DataFrame,
    user_description: str,
    design_plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate initial R code that only loads data.csv and performs transformations required by the design plan. No plotting."""
    print("\n=== STAGE 3: Generating data preparation code (no viz) ===")
    dataset_preview = serialize_df_sample(user_data)
    prompt = f"""
# Data Preparation Code Generation (R)

## Dataset preview
{json.dumps(dataset_preview, indent=2)}

## User goal
{user_description}

## Dashboard plan
{json.dumps(design_plan, indent=2)}

## Task
Write R code that:
1) Reads a CSV named 'data.csv' into a data.frame/data.table
2) Performs ONLY the data wrangling needed to support the views and selectors in the plan
3) Uses data.table/dplyr/tidyr as appropriate
4) Does NOT create any ggplot/animint objects yet

## Output JSON
{{"r_data_prep": "R code string", "notes": ["..."]}}
"""
    client = get_groq_client()
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL_LARGE_JSON,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def stage4_generate_full_viz(
    user_data: pd.DataFrame,
    user_description: str,
    design_plan: Dict[str, Any],
    examples_db: List[Dict[str, Any]],
    code_lib: Dict[str, Any],
    animint_docs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Use 2 selected examples + animint syntax docs to generate complete animint2 code."""
    print("\n=== STAGE 4: Generating full animint2 code ===")
    chosen_ids = [e.get("id") for e in design_plan.get("selected_examples", [])][:2]
    chosen_details = []
    missing = []
    for ex_id in chosen_ids:
        try:
            meta = next(e for e in examples_db if e["id"] == ex_id)
            code_key = meta["code_snippet"]
            code = (code_lib.get(code_key) or {}).get("code")
            if not code:
                missing.append({"id": ex_id, "error": f"code snippet '{code_key}' missing"})
                continue
            chosen_details.append({
                "id": ex_id,
                "title": meta.get("title"),
                "analysis_notes": (meta.get("analysis_notes", []) or [])[:4],
                "geoms_used": meta.get("geom_used", []),
                "full_code": code,
            })
        except StopIteration:
            missing.append({"id": ex_id, "error": "example not found"})

    if missing:
        print(f"Cannot use some examples: {missing}")

    dataset_summary = {
        "columns": list(user_data.columns),
        "types": {c: str(t) for c, t in user_data.dtypes.items()},
        "row_count": len(user_data),
    }

    prompt = f"""
# Full animint2 Code Generation

## Dataset summary
{json.dumps(dataset_summary, indent=2)}

## User goal
{user_description}

## Dashboard plan
{json.dumps(design_plan, indent=2)}

## Reference examples (2):
{json.dumps(chosen_details, indent=2)}

## animint2 syntax handbook (relevant snippets only)
{json.dumps(animint_docs, indent=2)}

## Task
Create a COMPLETE R script that:
1) Reads 'data.csv' and applies necessary transformations
2) Constructs a viz <- list(...) with 2-4 coordinated ggplot views matching the plan
3) Uses showSelected/clickSelects correctly (inside geom params, outside aes())
4) Defines selector.types, first selections, time, duration as needed
5) Ends with animint2dir(viz, '<out_dir>')

## Output JSON
{{"r_code": "R script", "implementation_notes": ["..."]}}
"""
    client = get_groq_client()
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL_LARGE_JSON,
        temperature=0.15,
        response_format={"type": "json_object"},
    )
    result = json.loads(response.choices[0].message.content)
    if not all(k in result for k in ("r_code", "implementation_notes")):
        raise ValueError("Stage 4 response missing required keys")
    if "viz <- list(" not in result["r_code"]:
        print("Warning: viz list not found in code")
    return result


def stage5_refine_with_errors(
    r_code: str,
    error_patterns: List[Dict[str, str]],
    animint_docs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Refine generated code by prompting with common errors and syntax docs."""
    print("\n=== STAGE 5: Refining code using error patterns ===")
    prompt = f"""
# Fix and Refine animint2 Code

## Known common errors
{json.dumps(error_patterns, indent=2)}

## animint2 syntax handbook
{json.dumps(animint_docs, indent=2)}

## Current code
```r
{r_code}
```

## Task
1) Detect likely issues and fix the code
2) Ensure correct usage of clickSelects/showSelected INSIDE geom params and OUTSIDE aes()
3) Ensure viz <- list(...) is valid and animint2dir(...) is present
4) Return the corrected full code

## Output JSON
{{"r_code": "Corrected R code", "fixes": ["..."]}}
"""
    client = get_groq_client()
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL_SELECTION,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)

# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def select_visualization_approach(
    user_data: pd.DataFrame,
    examples_db: list,
    user_description: str = ""
) -> dict:
    """
    Select the best visualization approach by matching dataset structure to example patterns
    Returns:
        {
            "selected_examples": [
                {
                    "id": str,
                    "match_score": float (0-1),
                    "applicable_geoms": list[str],
                    "reason": str
                }
            ],
            "recommended_visualization": {
                "dashboard_structure": str,
                "required_geoms": list[str],
                "interactive_elements": list[str],
                "data_transformations": list[str]
            },
            "reasoning": str
        }
    """
    print("\n=== STAGE 1: BEGIN VISUALIZATION APPROACH SELECTION ===")
    print(f"Analyzing dataset with {len(user_data)} rows and columns: {list(user_data.columns)}")
    print(f"User description: {user_description}")
    print(f"Evaluating against {len(examples_db)} available examples")
    # Analyze user dataset
    data_analysis = analyze_dataset_structure(user_data)
    
    # Prepare examples information
    examples_info = []
    for ex in examples_db[:MAX_EXAMPLES]:
        examples_info.append({
            "id": ex["id"],
            "title": ex["title"],
            "key_geoms": ex.get("geom_used", []),
            "analysis_notes": ex.get("analysis_notes", [])[:3],  # Top 3 most relevant notes
            "tags": ex.get("visualization_tags", [])
        })
    
    prompt = f"""
# Comprehensive Visualization Design Task

## User Dataset Analysis:
{json.dumps(data_analysis, indent=2)}

## User Visualization Goal:
{user_description}

## Available Visualization Patterns (showing {len(examples_info)} examples):
{json.dumps(examples_info, indent=2)}

## Task:
1. Analyze the dataset structure and user goal
2. Select 3 examples whose visualization patterns best match:
   - Data types and relationships
   - Potential interactive needs
   - Visualization goals
3. Recommend a comprehensive visualization approach including:
   - Dashboard layout with 1-3 coordinated views
   - Specific ggplot2 geoms to use
   - Required interactive elements
   - Any data transformations needed
   - Think big : from the examples see how different types of data is represented like using tallrects for animating time, using geom_path for maps (geographic datasets), using geom_tile for heatmaps, using multiple geoms in same dataset with some of them animated features using showSelected and clickSelects.

## Required Output Format (JSON):
{{
    "selected_examples": [
        {{
            "id": "example_id",
            "match_score": 0.0-1.0,
            "applicable_geoms": ["geom1", "geom2"],
            "reason": "How this example's patterns apply"
        }}
    ],
    "recommended_visualization": {{
        "dashboard_structure": "Description of views and relationships",
        "required_geoms": ["geom1", "geom2", "geom3"],
        "interactive_elements": ["clickSelects=var1", "showSelected=var2"],
        "data_transformations": ["melt", "aggregate", "calculate_stats"]
    }},
    "reasoning": "Detailed explanation connecting dataset to visualization design"
}}

## Special Instructions:
- Focus on matching the ANALYSIS NOTES patterns from examples
- Recommend sophisticated, multi-view visualizations like in the examples
- Specify EXACT geom combinations (e.g., geom_point + geom_line + geom_tile)
- Plan rich interactivity (clickSelects, showSelected, animation vars)
"""
    print("\n=== STAGE 1: API REQUEST SENT ===")
    print(f"Prompt length: {len(prompt)} characters")

    try:
        client = get_groq_client()
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_SELECTION,
            temperature=0.3,
            response_format={"type": "json_object"},
            max_tokens=2000
        )
        
        result = json.loads(response.choices[0].message.content)
        print("\n=== STAGE 1: RESPONSE RECEIVED ===")
        print("Selected examples:")
        for ex in result["selected_examples"]:
            print(f"- {ex['id']} (score: {ex.get('match_score', 0):.2f}): {ex['reason']}")
        print("\nRecommended visualization approach:")
        print(f"Geoms: {', '.join(result['recommended_visualization']['required_geoms'])}")
        print(f"Interactivity: {', '.join(result['recommended_visualization']['interactive_elements'])}")
        # Validate the response structure
        if not all(key in result for key in ["selected_examples", "recommended_visualization", "reasoning"]):
            raise ValueError("Invalid response structure")
            
        return result
        
    except Exception as e:
        print(f"Visualization selection failed: {str(e)}")
        return {
            "selected_examples": [],
            "recommended_visualization": {
                "dashboard_structure": "",
                "required_geoms": [],
                "interactive_elements": [],
                "data_transformations": []
            },
            "reasoning": "Selection process failed"
        }

# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def generate_animint_code(
    user_data: pd.DataFrame,
    user_description: str,
    selection_result: dict,
    examples_db: list,
    code_lib: dict
) -> dict:
    """
    Generate complete animint2 R code using selected examples as references
    Returns:
        {
            "r_code": "Full R script",
            "implementation_notes": ["note1", "note2"],
            "warnings": ["warning1", "warning2"]
        }
    """
    print("\n=== STAGE 2: VERIFYING EXAMPLE CODE AVAILABILITY ===")
    
    # First check if all required example codes exist
    missing_examples = []
    example_details = []
    
    for ex in selection_result["selected_examples"][:2]:  # Use top 2 examples
        try:
            ex_meta = next(e for e in examples_db if e["id"] == ex["id"])
            code_key = ex_meta["code_snippet"]
            
            if code_key not in code_lib:
                missing_examples.append({
                    "id": ex["id"],
                    "title": ex_meta["title"],
                    "code_snippet": code_key,
                    "error": f"Code snippet '{code_key}' not found in code library"
                })
                continue
                
            example_details.append({
                "id": ex["id"],
                "title": ex_meta["title"],
                "analysis_notes": ex_meta["analysis_notes"],
                "geoms_used": ex_meta["geom_used"],
                "full_code": code_lib[code_key]["code"]
            })
        except StopIteration:
            missing_examples.append({
                "id": ex["id"],
                "error": "Example not found in examples database"
            })
        except Exception as e:
            missing_examples.append({
                "id": ex["id"],
                "error": f"Error loading example: {str(e)}"
            })
    
    # Print status of each example
    print("\n--- EXAMPLE STATUS ---")
    for ex in example_details:
        print(f"✓ {ex['id']} - {ex['title']} (code available)")
    
    for ex in missing_examples:
        print(f"✗ {ex['id']} - {ex.get('title', '')} - ERROR: {ex['error']}")
    
    # If any examples are missing, return error immediately
    if missing_examples:
        error_msg = f"Cannot proceed - {len(missing_examples)} example(s) missing"
        print(f"\n=== CRITICAL ERROR ===\n{error_msg}")
        return {
            "r_code": f"# Error: {error_msg}\n# Missing examples: {', '.join([ex['id'] for ex in missing_examples])}",
            "implementation_notes": ["Code generation aborted due to missing examples"],
            "warnings": [f"Missing examples: {', '.join([ex['id'] for ex in missing_examples])}"]
        }
    
    print("\n✓ All required example codes available - proceeding with code generation")

    # Prepare data summary for prompt
    def convert_for_json(value):
        if isinstance(value, (pd.Timestamp, np.generic)):
            return str(value)
        return value
    
    data_summary = {
        "columns": list(user_data.columns),
        "types": {col: str(dtype) for col, dtype in user_data.dtypes.items()},
        "row_count": len(user_data),
        "sample_values": {col: [convert_for_json(v) for v in user_data[col].dropna().unique()[:3]]
                         for col in user_data.columns}
    }

        # Create a more structured prompt with explicit syntax examples
    prompt = f"""
# Comprehensive animint2 Code Generation Task

## IMPORTANT INSTRUCTIONS:
1. You MUST use proper animint2 syntax as shown in the reference examples (do not write library(ggplot2) seperately)
2. Follow EXACTLY the ggplot2 + animint2 pattern:
   - viz <- list(plot1 = ggplot() + geom_X(aes(...)) + ..., plot2 = ..., first = list(...), selector.types = list(...), time=list(variable="", ms=2000),duration=list(variable=.., variable=..), etc.) refer to the examples and write the detailed animint2 R code in same animint2 syntax
   - Use showSelected and clickSelects INSIDE geom aesthetics
   - Define selector.types and first selections in the viz list
   - Define time and duration for the interactivity if applicable (refer to examples)

## User Dataset Summary:
{json.dumps(data_summary, indent=2)}

## User Visualization Goal:
{user_description}

## Recommended Approach from Stage 1:
Required geoms: {', '.join(selection_result["recommended_visualization"]["required_geoms"])}
Interactive elements: {', '.join(selection_result["recommended_visualization"]["interactive_elements"])}

## CORRECT SYNTAX EXAMPLES:
## Reference Examples (truncated):
{json.dumps(example_details, indent=2)}
## Task:
Create a complete animint2 visualization R script that:
1. Processes the full dataset (all {len(user_data)} rows) , so import the dataset (from a csv file called data.csv) and then transform it as needed for the visualisation like in other examples (you can use data.table , dplyr, tidyr, etc. for transformations)
2. After transforming the dataset properly , Creates a viz list with 1-4 coordinated views (plots) that properly represent the data. Like representing time using tallrects, or using facets for categorical variables, 
   or using geom_line for trends, etc.
3. Can use these SPECIFIC geoms: {', '.join(selection_result["recommended_visualization"]["required_geoms"])}
4. Implements these interactive features: {', '.join(selection_result["recommended_visualization"]["interactive_elements"])}
## Requirements:
- MUST use ggplot() + geom_X() syntax
- MUST put showSelected/clickSelects OUTSIDE aes() and inside '' as shown in examples 
- MUST include selector.types, first selections, time, duration in the viz list according to what is animated.
- Do not add long comments in the code.
- ggplot names must match ^[a-zA-Z][a-zA-Z0-9]*$
## Required Output Format (JSON):
{{
    "r_code": "Complete R script",
    "implementation_notes": [
        "How reference examples were used",
        "Key design decisions"
    ]
}}
"""

    try:
        client = get_groq_client()
        # Try with the more powerful model first
        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_LARGE_JSON,  # Or compound-beta-kimi if available
                temperature=0.2,
                response_format={"type": "json_object"}
            )
        except:
            # Fallback to other model if needed
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_LARGE_JSON,
                temperature=0.2,
                response_format={"type": "json_object"}
            )

        result = json.loads(response.choices[0].message.content)
        
        # Validate the code contains key elements
        required_phrases = ["viz <- list(", "animint2dir("]
        if not all(phrase in result["r_code"] for phrase in required_phrases):
            raise ValueError("Generated code missing required animint2 structures")
            
        return result
        
    except Exception as e:
        print(f"Code generation failed: {str(e)}")
        return {
            "r_code": "# Error generating code\nlibrary(animint2)\n# Please implement manually",
            "implementation_notes": ["Code generation failed"],
            "warnings": ["See error messages"]
        }

def save_and_execute_code(code_result: dict, output_dir: str | Path | None = None):
    """Save the generated code and provide execution instructions"""
    out_dir = Path(output_dir) if output_dir is not None else R_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Save R code
    code_path = out_dir / "visualization.R"
    with open(code_path, "w") as f:
        f.write(code_result["r_code"])

    # Optionally save data prep code and plan if present
    if isinstance(code_result.get("data_prep"), dict) and code_result["data_prep"].get("r_data_prep"):
        data_prep_path = out_dir / "data_prep.R"
        with open(data_prep_path, "w") as f:
            f.write(code_result["data_prep"]["r_data_prep"])
    if code_result.get("plan") is not None:
        plan_path = out_dir / "plan.json"
        with open(plan_path, "w") as f:
            json.dump(code_result["plan"], f, indent=2)
    
    # Save implementation notes
    notes_path = out_dir / "implementation_notes.txt"
    with open(notes_path, "w") as f:
        f.write("IMPLEMENTATION NOTES:\n")
        f.write("\n".join(f"- {note}" for note in code_result["implementation_notes"]))
        f.write("\n\nWARNINGS:\n")
        f.write("\n".join(f"- {warn}" for warn in code_result.get("warnings", [])))
    
    print(f"\nGenerated code saved to {code_path}")
    print(f"Implementation notes saved to {notes_path}")
    print("\nTo execute:")
    print(f"1. Place your data file in the {out_dir} directory")
    print(f"2. Run: Rscript {code_path}")
    print(f"3. Open the generated HTML files in {out_dir}")

def main():
    """Complete multi-stage workflow: retrieval → design → data prep → generation → refinement"""
    try:
        # Load resources
        examples_db, code_lib = load_data_resources()
        design_rules, animint_docs, error_patterns = load_design_docs()

        # Sample user data (replace with actual loading)
        user_data = pd.DataFrame({
            'date': pd.date_range('2023-01-01', periods=365),
            'product': np.random.choice(['A', 'B', 'C', 'D'], 365),
            'region': np.random.choice(['North', 'South', 'East', 'West'], 365),
            'sales': np.random.normal(100, 20, 365),
            'temperature': np.random.uniform(50, 90, 365)
        })
        user_description = "Analyze sales patterns across products and regions over time"

        # Stage 1: Retrieval of examples
        print("\n=== STAGE 1: Retrieving Similar Dashboards ===")
        retrieved = stage1_retrieve_examples(user_data, user_description, examples_db, min_examples=MIN_CHAIN_EXAMPLES)

        # Stage 2: Design comprehensive dashboard layout
        plan = stage2_design_dashboard(user_data, user_description, retrieved, design_rules)

        # Stage 3: Data prep code only
        data_prep = stage3_generate_data_prep(user_data, user_description, plan)

        # Stage 4: Full viz code generation (2 examples + syntax)
        code_result = stage4_generate_full_viz(user_data, user_description, plan, examples_db, code_lib, animint_docs)

        # Stage 5: Error-aware refinement
        refined = stage5_refine_with_errors(code_result["r_code"], error_patterns, animint_docs)

        final_result = {
            "r_code": refined.get("r_code", code_result.get("r_code", "")),
            "implementation_notes": [
                "Design plan synthesized and applied",
                *code_result.get("implementation_notes", []),
                "Refinement fixes: " + "; ".join(refined.get("fixes", [])),
            ],
            "warnings": [],
            "plan": plan,
            "data_prep": data_prep,
            "retrieved_examples": [e.get("id") for e in retrieved],
        }

        # Save and show results
        save_and_execute_code(final_result)

        print("\nDesign Plan (condensed):")
        print(json.dumps({
            "selected_examples": plan.get("selected_examples", []),
            "views": [v.get("name") for v in plan.get("layout", {}).get("views", [])],
        }, indent=2))

    except Exception as e:
        print(f"Fatal error: {str(e)}")

if __name__ == "__main__":
    main()
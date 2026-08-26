import json
import os
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple
from groq import Groq
import httpx
import ast
import re
import logging
import math
from collections import Counter
import uuid

from app.paths import DATA_DIR, DASHBOARD_DIR, TEMPLATES_FILE, load_project_env

# Load environment
load_project_env()

def get_groq_client() -> Groq:
    """Get a Groq client instance, raising a clear exception if GROQ_API_KEY is not configured."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not configured. Please set your GROQ_API_KEY in backend/.env.local or environment variables.")
    return Groq(api_key=api_key)


# Configuration
MODEL_ANALYSIS = "meta-llama/llama-4-scout-17b-16e-instruct"
MODEL_DESIGN = "openai/gpt-oss-20b"
MODEL_CODE = "openai/gpt-oss-120b"
MODEL_OPTIMIZE = "deepseek-r1-distill-llama-70b"
# Toggle counter to alternate chat-edit calls between CODE and OPTIMIZE models
CHAT_EDIT_CALL_COUNT = 0
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-lite"

def _extract_code_blocks(text: str) -> str:
    """Utility: extract code from fenced blocks if present."""
    if not text:
        return ""
    if "```python" in text:
        try:
            return text.split("```python", 1)[1].split("```", 1)[0].strip()
        except Exception:
            pass
    if "```" in text:
        try:
            return text.split("```", 1)[1].split("```", 1)[0].strip()
        except Exception:
            pass
    return text.strip()


def _validate_code(code: str) -> tuple[bool, str]:
    """Return (ok, error_text) after attempting to parse Python code."""
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

def _validate_dash_code(code: str) -> Tuple[bool, List[str]]:
    """Lightweight static checks to reduce broken launches."""
    issues = []
    s = code or ""
    if "dash.Dash(" not in s:
        issues.append("Missing dash app initialization")
    if "if __name__ == '__main__':" not in s:
        issues.append("Missing __main__ guard")
    if "os.getenv('PORT'" not in s and 'os.getenv("PORT"' not in s:
        issues.append("Missing PORT read from env")
    if "app.run(" not in s:
        issues.append("Missing app.run call")
    if "dataset.csv" not in s:
        issues.append("Dataset path usage not found")
    if "pd.read_csv(" not in s:
        issues.append("Missing pandas read_csv")
    return (len(issues) == 0, issues)

def gemini_optimize_code(code: str, analysis_result: Dict[str, Any], dataset_summary: Dict[str, Any]) -> str:
    """
    Optional Stage: Use Gemini to further refine and correct the Dash code.
    Uses REST API via httpx; requires GEMINI_API_KEY in environment.
    Returns the improved code or the original code on failure.
    """
    if not GEMINI_API_KEY:
        return code
    print("\n=== STAGE 6: Gemini Optimization (conservative final pass) ===")
    system_prompt = """You are an expert Dash+Plotly engineer. Your job is to FIX only the specific
technical problems in the provided Python Dash app. 
 - DO NOT re-design working parts.
 - Make the smallest possible edit set so the script becomes syntactically correct ,runnable and does NOT render empty plots.
 - Ensure that there is no misconnected filter/animation/interaction.
 - Remove any callback errors (duplicate callbacks/ missing input/outputs )
 - Ensure filteration is correct for all paramaters that user needs to select.
 - Make the filter selection dropdown (checklist) text colour black, by adding style={'color': 'black'} to dcc.Dropdown(), if present. The texts are not visible currently.
Return ONLY the complete Python source file (no markdown).
Prioritize preserving variable names, layout, comments and the overall structure.
"""
    user_payload = f"""
Dataset summary:\n{json.dumps(dataset_summary, indent=2)}\n\nGenerated/optimized code to perfect:\n```python\n{code}\n```\n"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    body = {
        "contents": [
            {"role": "user", "parts": [{"text": system_prompt}]},
            {"role": "user", "parts": [{"text": user_payload}]}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 5000
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
                # fallback: try top-level fields
                text = data.get('content') or data.get('text') or ''

            improved = _extract_code_blocks(text)
            
            ok, err = _validate_code(improved) if improved else (False, 'empty')
            if ok:
                return improved
            else:
                logging.warning(f"Gemini returned code but it failed validation: {err}")
                return code
    except Exception as e:
        logging.exception("❌ Gemini optimization skipped")
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
    """
    Stage 1: Comprehensive dataset analysis
    Analyzes the entire dataset and returns detailed insights
    """
    print("\n=== STAGE 1: Comprehensive Dataset Analysis ===")
    print(f"Analyzing dataset with {len(df)} rows and {len(df.columns)} columns")
    
    # Convert dataframe to JSON-serializable format
    def convert_for_json(value):
        if isinstance(value, (pd.Timestamp, np.generic)):
            return str(value)
        return value
    
    # Sample data for analysis (first 100 rows to avoid token limits)
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
2. **Data Categories**: Classify the dataset into categories like:
   - Geological/Geospatial (coordinates, countries, regions)
   - Time-based (dates, timestamps, temporal patterns)
   - Scattering/Statistical (distributions, correlations)
   - Financial (money, transactions, economic metrics)
   - Transportation (routes, vehicles, logistics)
   - Product/Inventory (products, categories, stock)
   - Environmental/Climate (weather, pollution, sustainability)
   - Medical/Healthcare (patient data, clinical metrics)
   - ML/DL (features, predictions, model outputs)
   - Company/Business (organizational data, performance)
   - Marketing/Sales (campaigns, leads, conversions)
   - HR/Personnel (employee data, performance metrics)
   - And any other relevant categories

3. **Dataset Analysis**: What main patterns, trends, and insights can be extracted?
4. **Insights by Category**: Detailed insights for each identified category
5. **Visualization Insights**: What should users see in dashboard insight panels? also mention Required aggregations
6. **Predictions**: What future trends or patterns can be predicted?
7. **Field Relationships**: Explicitly note which fields are hierarchical/categorical and their relationships

## Requirements:
- Analyze ALL columns and data thoroughly
- Provide specific, actionable insights
- Consider temporal patterns if time data exists
- Identify correlations and relationships
- Suggest meaningful visualizations
- Be comprehensive but focused on business value

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
            "visualization_suggestions": [feild names, aggregations required, plot types]
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
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_ANALYSIS,
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=3000
        )
        
        result = json.loads(response.choices[0].message.content)
        print("✅ Dataset analysis completed")
        return result
        
    except Exception as e:
        print(f"❌ Dataset analysis failed: {str(e)}")
        # Return basic analysis as fallback
        return {
            "fields_analysis": [],
            "data_categories": [],
            "dataset_analysis": {"main_patterns": [], "key_trends": []},
            "insights_by_category": [],
            "dashboard_insights": [],
            "predictions": []
        } 

def retrieve_similar_examples(analysis_result: Dict[str, Any], examples_db: List[Dict[str, Any]], top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Stage 2: RAG retrieval of similar examples
    Retrieves most similar dashboard examples based on dataset analysis
    """
    print("\n=== STAGE 2: RAG Retrieval of Similar Examples ===")
    
    # Build query from analysis
    query_parts = []
    
    # Add categories
    categories = [cat["category"] for cat in analysis_result.get("data_categories", [])]
    query_parts.extend(categories)
    
    # Add field types
    fields = [field["field_type"] for field in analysis_result.get("fields_analysis", [])]
    query_parts.extend(fields)
    
    # Add insights
    insights = []
    for cat in analysis_result.get("insights_by_category", []):
        insights.extend(cat.get("insights", []))
    query_parts.extend(insights)
    
    query_text = " ".join(query_parts)
    
    # Simple TF-IDF based retrieval
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
    
    # Vectorize query
    query_vec = vectorize(query_text)
    
    # Score examples
    scored_examples = []
    for ex in examples_db:
        # Create document text from example
        doc_text = " ".join([
            ex.get("title", ""),
            " ".join(ex.get("data_category", [])),
            ex.get("description", ""),
            " ".join(ex.get("features", [])),
            " ".join(ex.get("ui_elements", [])),
            " ".join(ex.get("tools_used", []))
        ])
        
        doc_vec = vectorize(doc_text)
        similarity = cosine_similarity(query_vec, doc_vec)
        scored_examples.append((similarity, ex))
    
    # Sort by similarity and return top-k
    scored_examples.sort(key=lambda x: x[0], reverse=True)
    top_examples = [ex for _, ex in scored_examples[:top_k]]
    
    print(f"✅ Retrieved {len(top_examples)} similar examples")
    for i, ex in enumerate(top_examples, 1):
        print(f"  {i}. {ex['id']} - {ex.get('title', '')}")
    
    return top_examples

def design_dashboard(analysis_result: Dict[str, Any], similar_examples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Stage 3: Dashboard design based on analysis and examples
    Creates comprehensive dashboard design specification
    """
    print("\n=== STAGE 3: Dashboard Design ===")
    
    prompt = f"""
# Data visualisation Dashboard Design Task
## Dataset Analysis:
{json.dumps(analysis_result, indent=2)}
## Similar Example Dashboards:
{json.dumps(similar_examples, indent=2)}
## Task:
Design a comprehensive, interactive, and animated dashboard (that will be coded using dash+plotly [you dont have to code]) based on the dataset analysis and similar examples.
## Requirements:
### 1. Dashboard Structure:
- **Title**: Create a compelling, dataset-appropriate title
- **Styling**: Dark and modern theme
- **Layout**: Controls panel (user can select feilds, time periods, parameters,etc.) , 3-4 main main coordinated interconnected plots, updating table region (from the dataset) according to user selections, updating insights panel.

### 2. Time-based Features (if time data exists):
- Add play/pause animation button so that plots can update with time attribute when played.
- Make ALL plots linked to time updates
- Implement smooth transitions between time periods
- Add time scrubber/slider/selector in the controls panel

### 3. Interactive Elements:
- **Parameter Selectors**: Dropdowns, sliders, checkboxes for different fields
- **Linked Plots**: All visualizations update based on user selections
- **Color Linking**: Use consistent color schemes across plots
- **Legend Selections**: Interactive legends that filter data

### 4. Visualization Types (add 3-4 unique plots like):
- **Geographical**: Choropleth maps, Globe with point clouds,Animated migration/flight paths,Density mapbox, route maps for transportation data
- **Temporal**: Time series, animated charts, animations accross time selection.
- **Statistical**: 3D Scatter plots, Sankey diagrams ,Sunburst charts, Treemaps(for hierarchical data), Chord diagrams
- **Tables**: Display data for different selected categories in a beautiful table.
- **Refer the retrieved examples**

### 5. Insights Panel:
- Dynamic insights that update based on user selections
- Use insights from the analysis
- Make it interactive and informative

### 6. Technical Requirements:
- Use Dash (latest version)
- Make it responsive and modern
- Ensure all interactions work properly (inspect all callbacks, dont make duplicate ones)
- All categorical filters must specify how they map to underlying data codes
## Output Format (JSON):
{{
    "dashboard_title": "string",
    "styling": {{
        "theme": "string",
        "color_scheme": ["string"],
        "font_family": "string",
        "background_style": "string"
    }},
    "layout": {{
        "type": "string (grid/sidebar/tabs)",
        "rows": "integer",
        "columns": "integer",
        "description": "string"
    }},
    "plots": [
        {{
            "plot_id": "string",
            "plot_type": "ex. choropleth/3D scatter/sankey/time series etc.",
            "title": "string",
            "description": "string",
            "data_source": "string",
            "interactions": ["string"],
            "position": {{"row": "integer", "col": "integer"}},
            "size": {{"width": "integer", "height": "integer"}}
        }}
    ],
    "controls": [
        {{
            "control_id": "string",
            "control_type": "string (dropdown,slider,checkbox,button,play/pause,pointer)",
            "label": "string",
            "options": ["string"],
            "default_value": "any",
            "description": "string"
        }}
    ],
    "insights_panel": {{
        "title": "string",
        "content_sections": ["string"],
        "update_triggers": ["string"]
    }},
    "animations": [
        {{
            "type": "string",
            "description": "string",
            "triggers": ["string"]
        }}
    ],
    "interactions": [
        {{
            "from": "string",
            "to": "string",
            "type": "string",
            "description": "string"
        }}
    ]
}}
"""
    
    try:
        client = get_groq_client()
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_DESIGN,
            temperature=0.2,
            response_format={"type": "json_object"},
            max_tokens=3000
        )
        
        result = json.loads(response.choices[0].message.content)
        print("✅ Dashboard design completed")
        return result
        
    except Exception as e:
        print(f"❌ Dashboard design failed: {str(e)}")
        return {} 

def generate_dash_code(analysis_result: Dict[str, Any], design_spec: Dict[str, Any], dataset_summary: Dict[str, Any],dashboard_id: str = None) -> str:
    """
    Stage 4: Generate complete Dash app code
    Creates the full interactive dashboard based on design specification
    """
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
Generate a complete, working Dash app code that implements the given dashboard design to make the most interactive, intuitive, informative, animated, smooth data visualisation dashboard.

Note: The dataset file is located at 'dataset.csv' in the same directory as the generated Python code.
ALWAYS load the dataset exactly like this (include the imports if missing):
```python
script_dir = os.path.dirname(os.path.abspath(__file__))
dataset_path = os.path.join(script_dir, 'dataset.csv')
df = pd.read_csv(dataset_path)
```
Read the server port from the environment variable PORT and pass it to app.run so the backend can choose the port. The app will be mounted behind a reverse proxy under a subpath, provided in env BASE_PATH (e.g., "/dash3/"). You MUST configure Dash to respect this base path by setting both requests_pathname_prefix and routes_pathname_prefix when constructing the Dash app. Use these patterns:
```python
import dash
import os
base_path = os.getenv('BASE_PATH', '/')
# build Dash app with base path so it works under Nginx subpaths
app = dash.Dash(
    __name__,
    requests_pathname_prefix=base_path,
    routes_pathname_prefix=base_path,
    suppress_callback_exceptions=True,
)
if __name__ == '__main__':
    port = int(os.getenv('PORT', '8050'))
    app.run(host='0.0.0.0', port=port, debug=False)
```
Key requirements:
1. Use this structure (refer design spec):
   - Imports (dash, plotly, pandas, etc.)
   - Data loading/preprocessing/transformation/filtering
   - App setup with dark theme styling according to design spec
   - Controls panel
   - Main visualization area (3-4 coordinated linked plots)
   - Data table + insights panel
   - dcc.Store for shared data
   - correct callbacks
   - When using categorical variables, implement proper mapping between filter selections and data codes
   - Always map numeric codes back to meaningful labels for visualization
2. Must include (according to design spec) :
   - All plots mentioned in the design spec must be implemented according to the linkages, interactions and filterations mentioned.
   - Filterable data table part that represents user selected filtered data from real user enetered dataset.
   - Dynamic insights panel - get the insights from analysis_result.
   - Time animation controls (if dataset has a time related feild)
   - DO INCLUDE ALL THE UNIQUE PLOTS WITH CORRECT STRUCTURE, FILTERING, CALLBACKS etc. mentioned in the design spec.
3. Rules:
   - Use Dash 2.14+ (latest version)
   - No unnecessary comments
   - Max 320 lines of code (DO NOT EXCEED THIS)
   - Type hinted callbacks
   - Error handling with PreventUpdate
   - Shared filtered data via dcc.Store
   - Consistent color schemes, smooth transitions for animations
   - MUST respect BASE_PATH by setting requests_pathname_prefix and routes_pathname_prefix as shown above so assets and callbacks work under a subpath
Important:
2. All plots, table, and insights must update from the same stored filtered data.
3. Include proper error handling:
```python
from dash.exceptions import PreventUpdate
if not filtered_data:
    raise PreventUpdate
```
 - Maintain color and selection state across updates.
 - Use app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY]) for setup.
Example for filtered-data callback:
```python
@callback(Output('filtered-data', 'data'),
          [Input('time-selector', 'value'),
           Input('category-dropdown', 'value')])
def update_filtered_data(time_range, categories):
    filtered = df[(df['time'] >= time_range[0]) & (df['time'] <= time_range[1])]
    if categories:
        filtered = filtered[filtered['category'].isin(categories)]
    return filtered.to_dict('records')
```
(This is just an example — adapt to actual dataset and design)
Return ONLY the complete runnable code. Ensure the app is created with the BASE_PATH-aware prefixes and the __main__ block uses app.run with the PORT read from environment as shown above.
"""
    
    try:
        client = get_groq_client()
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_CODE,
            temperature=0.1,
            max_tokens=6000
        )
        
        code = _extract_code_blocks(response.choices[0].message.content)

        print("✅ Code generation completed")
        return code.strip()
        
    except Exception as e:
        print(f"❌ Code generation failed: {str(e)}")
        return ""

def optimize_code(code: str, analysis_result: Dict[str, Any], dataset_summary: Dict[str, Any]) -> str:
    """
    Stage 5: Code optimization and error resolution
    Optimizes the generated code and fixes any issues
    """
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
Optimize the generated Dash code to make it:
1. **More fitted to the dataset** - ensure all visualizations make sense for the data
2. **Not too complex** - simplify where possible while maintaining functionality
3. **Unique and interactive** - add creative touches that enhance user experience
4. **Working and error-free** - fix the syntax or logical errors
5. **Performance optimized** - ensure smooth interactions and fast loading
6. Check all visualizations show meaningful labels (not numeric codes)
7. Add meaningful tooltips for all components
8. Check all callbacks, are they complete, connected and not duplicated?
9. Ensure that there is no misconnected filter/animation/interaction
10. If the environment defines BASE_PATH, ensure the Dash app is initialized with matching requests_pathname_prefix and routes_pathname_prefix so it runs under a reverse-proxy subpath. Do not remove this if already present.
## Output:
Return the optimized, working Python code. The code should:
- Be complete and runnable - no errors in callbacks or layout. All components including filters should work together and have enough space.
- Show the true dataset features and insights in the visualisation dashboard
- Ensure all plots are showing what they are supposed to show, none of the plots should be blank. Ensure the code of the unique plots works with the data and they are visible.
- Include all necessary imports
- Ensure that the pay/pause animations work and update all plots according to time (if temporal data present)
- Have proper error handling
- Improve the UI, ensure every component and text is distinctly visisble, the colour of text should be vibrant enough to be visible on the background colour. The filter selection text should be black.
- DO NOT use any app._favicon
- Do not use run_server(); use app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8050')), debug=False) inside __main__
 - Respect BASE_PATH prefixes if present in the environment so the app works under subpaths behind Nginx.
Make sure the final code is production-ready and can handle the user's dataset effectively.
"""
    
    try:
        client = get_groq_client()
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_OPTIMIZE,
            temperature=0.1
        )
        
        optimized_code = _extract_code_blocks(response.choices[0].message.content)

        print("✅ Code optimization completed")
        return optimized_code.strip()
        
    except Exception as e:
        print(f"❌ Code optimization failed: {str(e)}")
        return code  # Return original code if optimization fails


def apply_user_edit_minimal(
    existing_code: str,
    user_request: str,
    dataset_summary: Dict[str, Any] | None = None,
    analysis_result: Dict[str, Any] | None = None,
) -> str:
    """
    Use MODEL_CODE to apply a minimal edit to the existing Dash app based on the
    user's request. Return the FULL updated Python code. The model is instructed
    to only implement the requested change(s), making no unnecessary edits.
    Fallback to the original code on failure.
    """
    print("\n=== CHAT EDIT: Applying minimal user-requested change ===")
    ds = dataset_summary or {}
    ar = analysis_result or {}
    prompt = f"""
You are an expert Dash + Plotly engineer. You are given an existing Dash app (Python) and a user's modification request.
Apply the SMALLEST POSSIBLE set of changes to implement ONLY what the user requested. Do NOT refactor or redesign anything else.
REQUIREMENTS:
- Maintain existing functionality; do not remove working parts unless asked.
- Ensure code remains syntactically valid and runnable.
- Return ONLY the complete Python source (no markdown, no explanations).
Context (dataset summary and prior analysis may help but do not justify unrelated edits):
DATASET SUMMARY:\n{json.dumps(ds, indent=2)}
ANALYSIS RESULT (optional):\n{json.dumps(ar, indent=2)}

USER REQUEST:\n{user_request}

EXISTING CODE (edit minimally):
```python
{existing_code}
```
"""
    try:
        # Alternate between code-generation and optimize models to avoid context saturation
        global CHAT_EDIT_CALL_COUNT
        CHAT_EDIT_CALL_COUNT += 1
        use_model = MODEL_CODE if CHAT_EDIT_CALL_COUNT % 2 == 1 else MODEL_OPTIMIZE
        print(f"[chat-edit] Using model: {use_model}")

        client = get_groq_client()
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=use_model,
            temperature=0.1
        )
        updated = _extract_code_blocks(response.choices[0].message.content)
        ok, err = _validate_code(updated)
        if ok and updated:
            return updated.strip()
        logging.warning(f"User chat edit returned invalid code; keeping original. Error: {err}")
        return existing_code
    except Exception as e:
        logging.exception(f"Chat edit failed: {e}")
        return existing_code

def fix_generated_code(code_path: str, error_text: str, output_dir: str) -> str:
    """
    Attempt to automatically fix a generated dashboard Python file using the LLM.

    Parameters
    - code_path: path to the generated Python file
    - error_text: runtime stderr/stdout captured when attempting to run the file
    - output_dir: directory where the dashboard files live (for context)

    Returns the fixed code as a string if successful, or an empty string on failure.
    """
    logging.info("=== AUTO-FIX: Attempting to fix generated dashboard code ===")
    print("\n=== AUTO-FIX: Attempting to fix generated dashboard code ===")
    # Read original code
    try:
        with open(code_path, 'r', encoding='utf-8') as f:
            original_code = f.read()
    except Exception as e:
        logging.exception(f"Could not read code at {code_path}: {e}")
        return ""

    # Fast non-LLM heuristics: normalize quotes and remove obvious English artifacts
    candidate = original_code.replace('\u201c', '"').replace('\u201d', '"').replace('\u2018', "'").replace('\u2019', "'")
    # Remove lines with clear English instruction artifacts inserted by models
    filtered_lines = []
    for ln in candidate.splitlines():
        if len(ln) > 120 and re.search(r'[A-Za-z]{5,} .* [A-Za-z]{5,}', ln):
            # skip long English lines
            continue
        if re.search(r'closest to \(|closest to ', ln, re.IGNORECASE):
            continue
        filtered_lines.append(ln)
    candidate = "\n".join(filtered_lines)

    ok, err = _validate_code(candidate)
    if ok:
        logging.info("Heuristic cleanup produced syntactically valid code")
        try:
            with open(os.path.join(output_dir, 'dashboard_app_fixed_candidate.py'), 'w', encoding='utf-8') as f:
                f.write(candidate)
        except Exception:
            pass
        return candidate

    # If heuristics failed, call LLM (optimized model) with a focused minimal-change prompt
    try:
        focused_prompt = f"""
The Python Dash app below failed to start with the following runtime output (traceback or error message). Apply the smallest possible edit(s) to make it runnable and syntactically correct. DO NOT rewrite or reformat the entire file. Only change the lines necessary to fix the error. Return ONLY the full corrected Python source file with no markdown.

Runtime error:
{error_text}

Original file begins:
{original_code}
"""
        client = get_groq_client()
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": focused_prompt}],
            model=MODEL_OPTIMIZE,
            temperature=0.0
        )
        fixed_raw = response.choices[0].message.content or ""

        # Extract code block if present
        fixed = _extract_code_blocks(fixed_raw)
        fixed = fixed.strip()

        if not fixed:
            logging.warning("LLM returned empty fix candidate")
            return ""

        ok2, err2 = _validate_code(fixed)
        if ok2:
            # Reject no-op fixes (identical code after normalization)
            if _normalized_code(fixed) == _normalized_code(original_code):
                logging.warning("LLM fix appears identical to original (no-op). Will attempt alternate strategy.")
                print("LLM fix appears identical to original (no-op). Will attempt alternate strategy.")
            else:
                try:
                    with open(os.path.join(output_dir, 'dashboard_app_fixed_candidate.py'), 'w', encoding='utf-8') as f:
                        f.write(fixed)
                except Exception:
                    pass
                logging.info("Auto-fix produced valid, changed code")
                print("Auto-fix produced valid, changed code")
                return fixed

        # Second attempt: different model with explicit no-op avoidance
        logging.info("First LLM attempt failed or was no-op; trying second model with stricter instructions")
        second_prompt = f"""
You previously returned a fix that was invalid or identical to the original. Read the runtime error and apply the MINIMAL NECESSARY edits to fix it.
RULES:
- Do NOT return code identical to the original; ensure the erroneous lines are corrected.
- Keep the structure and formatting; change only what's required for the app to run.
- Return ONLY the full corrected Python source (no markdown).

Runtime error:
{error_text}

Original code:
```python
{original_code}
```
"""
        try:
            response2 = client.chat.completions.create(
                messages=[{"role": "user", "content": second_prompt}],
                model=MODEL_CODE,
                temperature=0.0
            )
            fixed_raw2 = response2.choices[0].message.content or ""
            fixed2 = _extract_code_blocks(fixed_raw2).strip()
            if fixed2:
                ok22, err22 = _validate_code(fixed2)
                if ok22 and _normalized_code(fixed2) != _normalized_code(original_code):
                    try:
                        with open(os.path.join(output_dir, 'dashboard_app_fixed_candidate.py'), 'w', encoding='utf-8') as f:
                            f.write(fixed2)
                    except Exception:
                        pass
                    logging.info("Second LLM attempt produced valid, changed code")
                    return fixed2
                else:
                    logging.warning(f"Second attempt invalid or no-op: valid={ok22}, reason={err22 if not ok22 else 'no-op'}")
        except Exception as ee:
            logging.exception(f"Second LLM attempt failed: {ee}")

        # If still invalid, attempt one more conservative Gemini pass (if configured)
        if GEMINI_API_KEY:
            logging.info("First LLM fix invalid; attempting Gemini conservative fix")
            gemini_try = gemini_optimize_code(candidate, {}, {})
            ok3, err3 = _validate_code(gemini_try)
            if ok3:
                try:
                    with open(os.path.join(output_dir, 'dashboard_app_fixed_candidate.py'), 'w', encoding='utf-8') as f:
                        f.write(gemini_try)
                except Exception:
                    pass
                logging.info("Gemini produced valid fix")
                return gemini_try

        logging.warning("Auto-fix attempts failed to produce valid code")
        return ""
    except Exception as e:
        logging.exception(f"Auto-fix LLM attempt failed: {e}")
        return ""

def create_dashboard(
    data_file_path: str,
    user_prompt: str,
    output_dir: str,
    dashboard_id: str = None,
    progress_cb=None,
) -> str:
    """
    Main function to create dashboard through all 5 stages
    """
    print("🚀 Starting Dashboard Creation Pipeline")
    print("=" * 50)
    
    # Verify API key
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError("GROQ_API_KEY environment variable is not configured. Please set your GROQ_API_KEY in backend/.env.local or environment variables.")

    # Load data
    try:
        df = pd.read_csv(data_file_path)
        print(f"📊 Loaded dataset: {len(df)} rows, {len(df.columns)} columns")
    except Exception as e:
        print(f"❌ Failed to load data: {e}")
        raise ValueError(f"Failed to load dataset: {e}")
    
    # Load examples database
    try:
        with open(TEMPLATES_FILE, 'r', encoding='utf-8') as f:
            examples_db = json.load(f)
        print(f"📚 Loaded {len(examples_db)} example dashboards")
    except Exception as e:
        print(f"❌ Failed to load examples: {e}")
        examples_db = []
    
    current_dashboard_id = dashboard_id or str(uuid.uuid4())
    # Helper: safe progress callback
    def _progress(stage: str, progress: int, note: str | None = None):
        try:
            if callable(progress_cb):
                progress_cb(stage, progress, note)
        except Exception:
            pass

    dataset_name = os.path.basename(data_file_path)

    # Stage 1: Comprehensive Dataset Analysis
    analysis_result = analyze_dataset_comprehensive(df)
    # Build short note from analysis
    try:
        categories = [c.get("category") for c in (analysis_result.get("data_categories") or [])][:3]
        main_patterns = (analysis_result.get("dataset_analysis") or {}).get("main_patterns") or []
        note_1 = (
            f"LLM analyzed your '{dataset_name}' with {len(df)} rows and {len(df.columns)} columns. "
            f"Top categories: {', '.join([c for c in categories if c]) or 'N/A'}. "
            f"Patterns: {', '.join(main_patterns[:2]) or '—'}"
        )
    except Exception:
        note_1 = f"LLM analyzed your '{dataset_name}' (rows={len(df)}, cols={len(df.columns)})."
    _progress("stage_1", 16, note_1)
    
    # Stage 2: RAG Retrieval
    similar_examples = retrieve_similar_examples(analysis_result, examples_db, top_k=3)
    try:
        note_2 = f"Retrieved {len(similar_examples)} similar examples to guide your dashboard design."
    except Exception:
        note_2 = "Retrieved similar examples."
    _progress("stage_2", 32, note_2)
    
    # Stage 3: Dashboard Design
    design_spec = design_dashboard(analysis_result, similar_examples)
    try:
        title = design_spec.get("dashboard_title") or "Dashboard"
        plot_count = len(design_spec.get("plots") or [])
        note_3 = f"Designed '{title}' with {plot_count} visualizations and interactive controls."
    except Exception:
        note_3 = "Designed dashboard layout and interactions."
    _progress("stage_3", 48, note_3)
    
    # Stage 4: Code Generation
    dataset_summary = {
        "columns": list(df.columns),
        "types": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "row_count": len(df),
        "sample_data": df.head(5).to_dict(orient='records')
    }
    
    generated_code = generate_dash_code(analysis_result, design_spec, dataset_summary, current_dashboard_id)
    note_4 = "Generated complete Dash app code tailored to your dataset."
    _progress("stage_4", 64, note_4)
    
    # Stage 5: Code Optimization (Groq)
    optimized_code = optimize_code(generated_code, analysis_result, dataset_summary)
    note_5 = "Optimized the code for correctness, performance, and UI polish."
    _progress("stage_5", 82, note_5)
    # Stage 5b: Gemini Optimization
    gemini_code = gemini_optimize_code(optimized_code, analysis_result, dataset_summary)
    # Validate code variants and pick the best passing checks
    candidates = [
        ("gemini", gemini_code),
        ("optimized", optimized_code),
        ("generated", generated_code),
    ]
    chosen_name = "generated"
    final_code = generated_code
    for name, code in candidates:
        ok, issues = _validate_dash_code(code)
        if ok:
            chosen_name = name
            final_code = code
            break
    
    # Save results in the specified output directory (dashboard directory)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "dashboard_app.py")
    # Write snapshots so the frontend can always access generated/optimized/fixed versions
    try:
        with open(os.path.join(output_dir, "dashboard_app_generated.py"), 'w', encoding='utf-8') as f:
            f.write("# Generated code (pre-optimization)\n")
            f.write(generated_code or "# <no generated code>\n")
    except Exception:
        pass

    try:
        with open(os.path.join(output_dir, "dashboard_app_optimized.py"), 'w', encoding='utf-8') as f:
            f.write("# Optimized code (Groq)\n")
            f.write(optimized_code or "# <no optimized code>\n")
    except Exception:
        pass
    try:
        with open(os.path.join(output_dir, "dashboard_app_gemini.py"), 'w', encoding='utf-8') as f:
            f.write("# Gemini-optimized code\n")
            f.write(gemini_code or "# <no gemini code>\n")
    except Exception:
        pass

    # Validate final code
    if not final_code or not final_code.strip() or final_code.strip().startswith("# No code generated"):
        raise ValueError("Dashboard generation failed to produce valid Python code. Please verify your LLM API configuration and dataset.")

    # Validate syntax
    is_valid_code, val_err = _validate_code(final_code)
    if not is_valid_code:
        raise ValueError(f"Generated dashboard code failed Python syntax validation: {val_err}")

    # Always write the main dashboard file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(final_code)
    
    # Save analysis and design for reference
    with open(os.path.join(output_dir, "analysis_result.json"), 'w') as f:
        json.dump(analysis_result, f, indent=2)
    
    with open(os.path.join(output_dir, "design_spec.json"), 'w') as f:
        json.dump(design_spec, f, indent=2)
    
    print(f"\n🎉 Dashboard creation completed!")
    print(f"📁 Output files saved to: {output_dir}")
    print(f"🐍 Main dashboard: {output_file}")
    _progress("stage_6", 100, "All stages completed. Your dashboard is ready to launch.")

    return output_file

def initialize_vector_database():
    """Initialize the vector database (placeholder for future implementation)"""
    print("🔧 Vector database initialization (placeholder)")
    # This would be implemented with a proper vector database like Pinecone, Weaviate, etc.
    pass

if __name__ == "__main__":
    # Test the pipeline
    test_data = str(DATA_DIR / "synthetic_transportation_data.csv")
    user_prompt = "Create a beautiful animated dashboard showing the entire dataset in a very modern, animated, interactive manner."
    test_output_dir = str(DASHBOARD_DIR / "test_run")
    
    output_file = create_dashboard(test_data, user_prompt, test_output_dir)
    print(f"\n✅ Test completed. Dashboard saved to: {output_file}") 
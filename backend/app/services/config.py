"""
Configuration file for the new dashboard creation pipeline
"""

import os

from app.paths import CHROMA_DIR, DASHBOARD_DIR, ENV_FILE, TEMPLATES_FILE, load_project_env

# Load environment variables
load_project_env()

# Model Configuration (configurable via environment variables with valid Groq models)
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_MODEL_ANALYSIS = os.getenv("GROQ_MODEL_ANALYSIS", DEFAULT_GROQ_MODEL)
GROQ_MODEL_DESIGN = os.getenv("GROQ_MODEL_DESIGN", DEFAULT_GROQ_MODEL)
GROQ_MODEL_CODE = os.getenv("GROQ_MODEL_CODE", DEFAULT_GROQ_MODEL)
GROQ_MODEL_OPTIMIZE = os.getenv("GROQ_MODEL_OPTIMIZE", DEFAULT_GROQ_MODEL)

MODELS = {
    "analyzer": GROQ_MODEL_ANALYSIS,
    "designer": GROQ_MODEL_DESIGN, 
    "coder": GROQ_MODEL_CODE,
    "optimizer": GROQ_MODEL_OPTIMIZE,
}

# Vector Database Configuration
VECTOR_DB_CONFIG = {
    "persist_directory": str(CHROMA_DIR),
    "collection_name": "viz_examples",
    "embedding_space": "cosine"
}

# Pipeline Configuration
PIPELINE_CONFIG = {
    "max_examples_retrieved": 3,
    "analysis_sample_size": 5,
    "design_temperature": 0.3,
    "code_temperature": 0.1,
    "optimization_temperature": 0.1
}

# Output Configuration
OUTPUT_CONFIG = {
    "output_directory": str(DASHBOARD_DIR),
    "filename_prefix": "generated_dashboard",
    "timestamp_format": "%Y%m%d_%H%M%S"
}

# Default User Prompts
DEFAULT_PROMPTS = {
    "sales": "Create a beautiful animated dashboard showing sales trends by product and region with profit analysis, including interactive filters and time-based animations",
    "financial": "Create a professional financial dashboard with animated charts, correlation analysis, and interactive asset selection",
    "healthcare": "Create a medical performance dashboard with patient outcomes, resource utilization, and professional medical aesthetics",
    "environmental": "Create a climate monitoring dashboard with animated maps, trend analysis, and environmental insights",
    "general": "Create the best animated interactive dashboard that represents the entire dataset beautifully with linked plots"
}

# Validation
def validate_config():
    """Validate the configuration"""
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError("GROQ_API_KEY not found. Set it in backend/.env.local or the environment.")
    
    if not os.path.exists(TEMPLATES_FILE):
        raise ValueError(f"Templates file not found: {TEMPLATES_FILE}")
    
    return True

# Get configuration
def get_config():
    """Get the complete configuration"""
    return {
        "models": MODELS,
        "vector_db": VECTOR_DB_CONFIG,
        "pipeline": PIPELINE_CONFIG,
        "output": OUTPUT_CONFIG,
        "templates_file": str(TEMPLATES_FILE),
        "default_prompts": DEFAULT_PROMPTS
    }

if __name__ == "__main__":
    try:
        validate_config()
        print("✅ Configuration is valid")
        config = get_config()
        print(f"🔧 Using models: {config['models']}")
        print(f"📁 Templates: {config['templates_file']}")
    except Exception as e:
        print(f"❌ Configuration error: {e}") 
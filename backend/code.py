from app.paths import DASHBOARD_DIR, DATA_DIR
from app.services.prompt_chain_new import create_dashboard

output_file = create_dashboard(
    str(DATA_DIR / "synthetic_transportation_data.csv"),
    "create a interactive, animated, data visualisation dashboard for best insights of this data",
    str(DASHBOARD_DIR / "manual_run"),
)
print(f"Dashboard created: {output_file}")

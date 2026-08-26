import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import pandas as pd
import numpy as np
import datetime

# --- Generate synthetic transport data ---
np.random.seed(42)
routes = ["North Line", "East Line", "West Line"]
vehicle_types = ["Bus", "Tram"]
stops = [f"Stop {i}" for i in range(1, 12)]

df = pd.DataFrame([
    {
        "route": r,
        "stop": s,
        "lat": 34.05 + np.random.uniform(-0.03, 0.03),
        "lon": -118.25 + np.random.uniform(-0.03, 0.03),
        "boarding": np.random.randint(50, 500),
        "alighting": np.random.randint(50, 500),
        "vehicle": np.random.choice(vehicle_types),
        "date": datetime.date(2024, np.random.randint(1, 12), np.random.randint(1, 28))
    }
    for r in routes for s in stops
])

# --- App ---
app = dash.Dash(__name__)

app.layout = html.Div([
    html.Div([
        html.H3("🚏 Transportation Analytics"),
        dcc.Dropdown(routes, routes[0], id="route"),
        dcc.Dropdown(vehicle_types, vehicle_types[0], id="vehicle"),
        dcc.DatePickerSingle(
            id="date", min_date_allowed=df.date.min(),
            max_date_allowed=df.date.max(), date=df.date.min()
        ),
        html.Div(id="kpi", style={"marginTop": "20px"})
    ], style={"width": "20%", "display": "inline-block", "verticalAlign": "top"}),

    html.Div([
        dcc.Graph(id="map", style={"height": "60vh"}),
        dcc.Graph(id="bar")
    ], style={"width": "75%", "display": "inline-block"})
])

@app.callback(
    [Output("map", "figure"), Output("bar", "figure"), Output("kpi", "children")],
    [Input("route", "value"), Input("vehicle", "value"), Input("date", "date")]
)
def update_dashboard(route, vehicle, date):
    filtered = df[(df.route == route) & (df.vehicle == vehicle) & (df.date == pd.to_datetime(date).date())]
    
    # KPIs
    total = filtered.boarding.sum()
    avg_daily = int(total / len(stops))
    avg_trip = int(total / max(1, len(filtered)))
    kpi_text = html.Div([
        html.H4("KPIs"),
        html.P(f"Total Ridership: {total}"),
        html.P(f"Avg Riders/Stop: {avg_daily}"),
        html.P(f"Avg Riders/Trip: {avg_trip}")
    ])
    
    # Map plot
    fig_map = px.scatter_mapbox(
        filtered, lat="lat", lon="lon", size="boarding", color="boarding",
        hover_name="stop", zoom=12, height=400, color_continuous_scale="Turbo"
    )
    fig_map.update_layout(mapbox_style="carto-positron", margin={"r":0,"t":0,"l":0,"b":0})

    # Bar chart
    fig_bar = px.bar(filtered, x="stop", y=["boarding", "alighting"], barmode="group",
                     title="Boarding vs Alighting", color_discrete_sequence=["#1f77b4", "#ff7f0e"])
    
    return fig_map, fig_bar, kpi_text

if __name__ == "__main__":
    app.run(debug=True)
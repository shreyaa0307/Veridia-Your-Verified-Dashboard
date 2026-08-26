import dash
from dash import html, dcc, Input, Output
import plotly.express as px
import pandas as pd, numpy as np

# ---------- Synthetic data ----------
np.random.seed(0)
routes = ["North", "South", "East"]
vehicles = ["Bus", "Tram"]
stops = [f"Stop {i}" for i in range(1, 12)]
dates = pd.date_range("2024-01-01", periods=30)

data = []
for r in routes:
    for v in vehicles:
        for s in stops:
            for d in dates:
                b = np.random.randint(50, 500)
                data.append({
                    "route": r, "vehicle": v, "stop": s,
                    "lat": 34.05 + np.random.uniform(-0.02, 0.02),
                    "lon": -118.25 + np.random.uniform(-0.02, 0.02),
                    "boarding": b, "alighting": np.random.randint(30, b),
                    "revenue": b * np.random.uniform(1.5, 3),
                    "crowding": np.random.uniform(0, 1), "date": d
                })
df = pd.DataFrame(data)

# ---------- App ----------
app = dash.Dash(__name__)
map_styles = ["carto-positron", "open-street-map", "stamen-terrain", "stamen-toner", "stamen-watercolor"]

app.layout = html.Div([
    html.Div([
        html.H3("🚍 Transport Ops Dashboard"),
        html.Label("Select Route"), dcc.Dropdown(routes, routes[0], id="route"),
        html.Label("Select Vehicle"), dcc.Dropdown(vehicles, vehicles[0], id="vehicle"),
        html.Label("Select Date"), dcc.DatePickerSingle(id="date", date=dates[0]),
        html.Label("Crowding Threshold"), dcc.Slider(min=0, max=1, step=0.05, value=0.5, id="crowd_th", marks=None, tooltip={"placement": "bottom"}),
        html.Label("Boarding Range"), dcc.RangeSlider(50, 500, 10, value=[50, 500], id="boarding_range"),
        html.Label("Map Style"), dcc.Dropdown(map_styles, map_styles[0], id="map_style"),
        html.Div(id="kpis", style={"marginTop": "20px", "padding": "10px", "background": "#f4f4f4"})
    ], style={"width": "22%", "display": "inline-block", "verticalAlign": "top", "padding": "10px"}),

    html.Div([
        dcc.Graph(id="map", style={"height": "50vh"}),
        dcc.Graph(id="bar", style={"height": "25vh", "marginTop": "10px"}),
        dcc.Graph(id="scatter3d", style={"height": "35vh", "marginTop": "10px"}),
        html.Div(id="insights", style={"padding": "10px", "background": "#f9f9f9", "marginTop": "10px"})
    ], style={"width": "75%", "display": "inline-block", "paddingLeft": "2%"})
])

# ---------- Callback ----------
@app.callback(
    [Output("map", "figure"), Output("bar", "figure"), Output("scatter3d", "figure"),
     Output("kpis", "children"), Output("insights", "children")],
    [Input("route", "value"), Input("vehicle", "value"), Input("date", "date"),
     Input("crowd_th", "value"), Input("boarding_range", "value"), Input("map_style", "value")]
)
def update(route, vehicle, date, crowd_th, boarding_range, map_style):
    # Filter data
    f = df[
        (df.route == route) & (df.vehicle == vehicle) &
        (df.date == pd.to_datetime(date)) &
        (df.crowding >= crowd_th) &
        (df.boarding >= boarding_range[0]) &
        (df.boarding <= boarding_range[1])
    ]

    # KPIs
    total_r = int(f.boarding.sum()) if not f.empty else 0
    avg_crowd = f.crowding.mean() * 100 if not f.empty else 0
    revenue = f.revenue.sum() if not f.empty else 0
    kpi = html.Div([
        html.H4("Key Performance Indicators"),
        html.P(f"Total Ridership: {total_r}"),
        html.P(f"Avg Crowding: {avg_crowd:.1f}%"),
        html.P(f"Revenue: ${revenue:,.0f}")
    ])

    # Map (animated by stop order)
    fig_map = px.scatter_mapbox(
        f.sort_values("stop"), lat="lat", lon="lon", hover_name="stop",
        color="boarding", zoom=12, size="boarding",
        color_continuous_scale="Turbo", animation_frame="stop"
    )
    if not f.empty:
        fig_map.add_trace(px.line_mapbox(f, lat="lat", lon="lon").data[0])
    fig_map.update_layout(mapbox_style=map_style, margin={"r":0,"t":0,"l":0,"b":0})

    # Passenger flow bar
    fig_bar = px.bar(f, x="stop", y=["boarding", "alighting"], barmode="group", title="Passenger Flow")

    # NEW: 3D Scatter plot
    fig_scatter3d = px.scatter_3d(
        f, x="boarding", y="alighting", z="crowding",
        color="boarding", size="revenue",
        hover_name="stop", title="Stop Performance: Boarding vs Alighting vs Crowding",
        color_continuous_scale="Viridis"
    )

    # Insights
    if not f.empty:
        top_stops = f.nlargest(3, "boarding")[["stop", "boarding"]]
        worst_stop = f.nsmallest(1, "boarding")[["stop", "boarding"]]
        insight_text = [
            html.P(f"Top 3 Stops: {', '.join(top_stops['stop'])}"),
            html.P(f"Lowest performing stop: {worst_stop.iloc[0]['stop']} ({worst_stop.iloc[0]['boarding']} riders)"),
            html.P("Recommendation: Consider redistributing vehicles towards high-ridership corridors.")
        ]
    else:
        insight_text = [html.P("No data matches the current filters.")]

    return fig_map, fig_bar, fig_scatter3d, kpi, html.Div(insight_text)

if __name__ == "__main__":
    app.run(debug=True)

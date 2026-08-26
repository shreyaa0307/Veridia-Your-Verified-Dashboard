import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import datetime

# --- Synthetic Data ---
np.random.seed(0)
players = {
    "Darius Garland": "https://cdn.nba.com/headshots/nba/latest/1040x760/1629636.png",
    "Stephen Curry": "https://cdn.nba.com/headshots/nba/latest/1040x760/201939.png",
    "LeBron James": "https://cdn.nba.com/headshots/nba/latest/1040x760/2544.png"
}
dates = pd.date_range("2020-12-01", "2021-07-01")
n = 500
df = pd.DataFrame({
    "player": np.random.choice(list(players.keys()), n),
    "date": np.random.choice(dates, n),
    "x": np.random.uniform(0, 94, n),
    "y": np.random.uniform(0, 50, n),
    "pass_dir": np.random.choice(['N','NE','E','SE','S','SW','W','NW'], n),
    "pass_dist": np.random.choice([10,20,30,40,50], n),
    "shot_clock": np.random.randint(0, 24, n)
})

# --- Dash App ---
app = dash.Dash(__name__)
app.layout = html.Div([
    # Left Panel
    html.Div([
        html.Img(id="player_img", style={"width": "100%"}),
        dcc.Dropdown(list(players.keys()), value="Darius Garland", id="player"),
        html.Label("Date Filter"), 
        dcc.DatePickerRange(id="date", start_date=dates.min(), end_date=dates.max()),
        html.Label("Shot Clock Filter"), 
        dcc.Slider(min=0,max=24,step=1,value=24,marks={i: str(i) for i in range(0, 25, 4)},id="shotclock"),
        html.Div([
            html.Button("All Teams Selected", id="btn1"),
            html.Button("All Shot Types Selected", id="btn2"),
            html.Button("All Quarters Selected", id="btn3")
        ], style={"marginTop": "10px", "display": "grid", "gap": "5px"})
    ], style={"width": "20%", "display": "inline-block", "verticalAlign": "top"}),

    # Middle Panel
    html.Div([
        dcc.Graph(id="heatmap"),
        html.Div([
            dcc.Graph(id="rose", style={"display":"inline-block", "width":"49%"}),
            dcc.Graph(id="barchart", style={"display":"inline-block", "width":"49%"})
        ])
    ], style={"width": "55%", "display": "inline-block"}),

    # Right Panel
    html.Div([
        html.H4("How to Interpret"),
        html.P("Synthetic example of NBA pass data. Heatmap shows pass origins, rose plot shows pass directions, bar shows assists vs. shot clock."),
        html.Label("Tooltips"), 
        dcc.RadioItems(["On", "Off"], "On", id="tooltip_toggle")
    ], style={"width": "20%", "display": "inline-block", "verticalAlign": "top"})
])

# --- Callbacks ---
@app.callback(
    [Output("player_img", "src"),
     Output("heatmap", "figure"),
     Output("rose", "figure"),
     Output("barchart", "figure")],
    [Input("player", "value"),
     Input("date", "start_date"),
     Input("date", "end_date"),
     Input("shotclock", "value")]
)
def update(player, start, end, sc):
    dff = df[(df["player"] == player) &
             (df["date"] >= pd.to_datetime(start)) &
             (df["date"] <= pd.to_datetime(end)) &
             (df["shot_clock"] <= sc)]

    # Heatmap with basketball court layout
    heat = go.Figure(go.Histogram2d(x=dff["x"], y=dff["y"], colorscale="Inferno"))
    heat.update_layout(title="Pass Origin Heatmap", xaxis=dict(visible=False), yaxis=dict(visible=False),
                       images=[dict(source="https://i.imgur.com/4HJbzEq.png",  # court background
                                    xref="x", yref="y", x=0, y=50, sizex=94, sizey=50, sizing="stretch", layer="below")])

    # Rose Plot
    rose = px.bar_polar(dff, r="pass_dist", theta="pass_dir", color="pass_dist",
                        color_continuous_scale=px.colors.sequential.Plasma)
    rose.update_layout(title="Passing Tendencies by Distance")

    # Bar Chart
    bar = px.histogram(dff, x="shot_clock", color="pass_dist", nbins=12)
    bar.update_layout(title="Assist Distribution by Shot Clock Time Left")
    return players[player], heat, rose, bar
if __name__ == "__main__":
    app.run(debug=True)

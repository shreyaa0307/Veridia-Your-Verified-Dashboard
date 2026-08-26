import json
import pandas as pd
import numpy as np
import dash
import dash_bootstrap_components as dbc
import plotly.express as px
from dash import dcc, html, dash_table, Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate

import os as _os
df = pd.read_csv(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'backend', 'data', 'world_environment_synthetic.csv'))
df["Year"] = df["Year"].astype(int)

# Helper for country codes (ISO-3) used by Plotly choropleth
country_iso = {
    "United States": "USA",
    "China": "CHN",
    "India": "IND",
    "Germany": "DEU",
    "Brazil": "BRA",
    "Japan": "JPN",
    "Russia": "RUS",
    "Canada": "CAN",
    "France": "FRA",
    "United Kingdom": "GBR"
}
df["iso_alpha"] = df["Country"].map(country_iso)

# -------------------- App Setup --------------------
app = dash.Dash(
    __name__, 
    external_stylesheets=[dbc.themes.DARKLY],
    meta_tags=[{'name': 'viewport', 'content': 'width=device-width, initial-scale=1'}]
)
app.title = "Global Development Dashboard"

# -------------------- Layout --------------------
controls = dbc.Card(
    [
        html.H5("Filters", className="mb-3"),
        dbc.Label("Select Countries", html_for="country_selector", className="mb-2"),
        dcc.Dropdown(
            id="country_selector",
            options=[{"label": c, "value": c} for c in sorted(df["Country"].unique())],
            value=["United States", "China", "India"],
            multi=True,
            clearable=False,
            className="mb-3"
        ),
        dbc.Label("Year Range", html_for="year_slider", className="mb-2"),
        dcc.RangeSlider(
            id="year_slider",
            min=df["Year"].min(),
            max=df["Year"].max(),
            value=[df["Year"].min(), df["Year"].max()],
            marks={y: str(y) for y in range(df["Year"].min(), df["Year"].max() + 1, 5)},
            tooltip={"placement": "bottom", "always_visible": False},
            className="mb-3"
        ),
        dbc.Label("Primary Metric", html_for="metric_selector", className="mb-2"),
        dcc.Dropdown(
            id="metric_selector",
            options=[
                {"label": "GDP per Capita", "value": "GDP_per_capita"},
                {"label": "Life Expectancy", "value": "Life_Expectancy"},
                {"label": "CO₂ per Capita", "value": "CO2_per_capita"}
            ],
            value="GDP_per_capita",
            clearable=False,
            className="mb-3"
        ),
        dbc.Button("Play/Pause", id="play_pause", n_clicks=0, color="primary", className="mb-2"),
        dcc.Interval(id="animation_interval", interval=1000, disabled=True, n_intervals=0)
    ],
    className="p-3 mb-4",
    color="dark"
)

insights_panel = dbc.Card(
    [
        html.H5("Key Insights", className="mb-3"),
        html.Div(id="insights_content")
    ],
    className="p-3 mb-4",
    color="dark"
)

# -------------------- Plots --------------------
# def create_choropleth(data, year, metric):
#     d = data[data["Year"] == year]
#     fig = px.choropleth(
#         d,
#         locations="iso_alpha",
#         color=metric,
#         hover_name="Country",
#         color_continuous_scale="Viridis",
#         title=f"{metric.replace('_', ' ')} in {year}",
#         projection_scale=4
#     )
#     fig.update_layout(
#         margin=dict(l=0, r=0, t=30, b=0),
#         paper_bgcolor="rgba(0,0,0,0)",
#         plot_bgcolor="rgba(0,0,0,0)"
#     )
#     return fig
def create_choropleth(data, year, metric):
    d = data[data["Year"] == year]
    fig = px.choropleth(
        d,
        locations="iso_alpha",
        color=metric,
        hover_name="Country",
        color_continuous_scale="Viridis",
        title=f"{metric.replace('_', ' ')} in {year}",
        projection="natural earth",  # Add this
        scope="world",  # Add this
        height=500  # Add fixed height
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        geo=dict(
            bgcolor='rgba(0,0,0,0)',
            landcolor='lightgray',
            showcountries=True
        )
    )
    return fig

def create_line_chart(data, countries):
    d = data[data["Country"].isin(countries)]
    fig = px.line(
        d,
        x="Year",
        y="GDP_per_capita",
        color="Country",
        title="GDP per Capita Trend",
        color_discrete_sequence=px.colors.qualitative.Plotly
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig

def create_bar_chart(data, year, countries):
    d = data[(data["Year"] == year) & (data["Country"].isin(countries))]
    fig = px.bar(
        d,
        x="Country",
        y="CO2_per_capita",
        color="Country",
        title=f"CO₂ per Capita in {year}",
        color_discrete_sequence=px.colors.qualitative.Plotly
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig

def create_scatter_plot(data, year, countries):
    d = data[(data["Year"] == year) & (data["Country"].isin(countries))]
    fig = px.scatter(
        d,
        x="GDP_per_capita",
        y="Life_Expectancy",
        color="Country",
        title=f"GDP per Capita vs Life Expectancy in {year}",
        color_discrete_sequence=px.colors.qualitative.Plotly
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig

def create_data_table(data):
    cols = ["Country", "Year", "GDP_per_capita", "Life_Expectancy", "Population", "CO2_per_capita"]
    return dash_table.DataTable(
        data=data[cols].to_dict("records"),
        columns=[{"name": c.replace("_", " "), "id": c} for c in cols],
        page_size=10,
        style_table={"overflowX": "auto", "height": "300px"},
        style_header={"backgroundColor": "#2c2c2c", "color": "white"},
        style_cell={"backgroundColor": "#1e1e1e", "color": "white"},
        sort_action="native",
        filter_action="native"
    )

# -------------------- Layout --------------------
app.layout = dbc.Container(
    [
        html.H1(
            "Global Development & Sustainability Dashboard",
            className="text-center my-4",
            style={"color": "#fff", "fontSize": "1.5rem"}
        ),
        dbc.Row(
            [
                dbc.Col(controls, width=3),
                dbc.Col(insights_panel, width=9)
            ],
            className="mb-4"
        ),
        dbc.Row(
            [
                dbc.Col(dcc.Graph(id="choropleth"), width=6),
                dbc.Col(dcc.Graph(id="line_chart"), width=6)
            ],
            className="mb-4"
        ),
        dbc.Row(
            [
                dbc.Col(dcc.Graph(id="scatter_plot"), width=6),
                dbc.Col(dcc.Graph(id="bar_chart"), width=6)
            ],
            className="mb-4"
        ),
        dbc.Row(
            dbc.Col(html.Div(id="data_table"), width=12)
        )
    ],
    fluid=True,
    style={"background": "#1a1a1a", "color": "#fff"}
)

# -------------------- Callbacks --------------------
@callback(
    Output("choropleth", "figure"),
    Input("year_slider", "value"),
    Input("metric_selector", "value"),
    Input("animation_interval", "n_intervals"),
    Input("play_pause", "n_clicks")
)
def update_choropleth(year_range, metric, n_intervals, play_clicks):
    try:
        year = year_range[1]
        data = df[(df["Year"] >= year_range[0]) & (df["Year"] <= year_range[1])]
        return create_choropleth(data, year, metric)
    except Exception as e:
        print(f"Error in choropleth callback: {e}")
        raise PreventUpdate

@callback(
    Output("line_chart", "figure"),
    Input("country_selector", "value"),
    Input("year_slider", "value")
)
def update_line_chart(countries, year_range):
    try:
        if not countries or not year_range:
            raise PreventUpdate
        data = df[(df["Country"].isin(countries)) & 
                  (df["Year"] >= year_range[0]) & 
                  (df["Year"] <= year_range[1])]
        return create_line_chart(data, countries)
    except Exception as e:
        print(f"Error in line chart callback: {e}")
        raise PreventUpdate

@callback(
    Output("scatter_plot", "figure"),
    Input("country_selector", "value"),
    Input("year_slider", "value")
)
def update_scatter_plot(countries, year_range):
    try:
        if not countries or not year_range:
            raise PreventUpdate
        year = year_range[1]
        data = df[(df["Country"].isin(countries)) & 
                  (df["Year"] >= year_range[0]) & 
                  (df["Year"] <= year_range[1])]
        return create_scatter_plot(data, year, countries)
    except Exception as e:
        print(f"Error in scatter plot callback: {e}")
        raise PreventUpdate

@callback(
    Output("bar_chart", "figure"),
    Input("country_selector", "value"),
    Input("year_slider", "value")
)
def update_bar_chart(countries, year_range):
    try:
        if not countries or not year_range:
            raise PreventUpdate
        year = year_range[1]
        data = df[(df["Country"].isin(countries)) & 
                  (df["Year"] >= year_range[0]) & 
                  (df["Year"] <= year_range[1])]
        return create_bar_chart(data, year, countries)
    except Exception as e:
        print(f"Error in bar chart callback: {e}")
        raise PreventUpdate

@callback(
    Output("data_table", "children"),
    Input("country_selector", "value"),
    Input("year_slider", "value")
)
def update_table(countries, year_range):
    try:
        if not countries or not year_range:
            raise PreventUpdate
        data = df[(df["Country"].isin(countries)) & 
                  (df["Year"] >= year_range[0]) & 
                  (df["Year"] <= year_range[1])]
        return create_data_table(data)
    except Exception as e:
        print(f"Error in table callback: {e}")
        raise PreventUpdate

@callback(
    Output("insights_content", "children"),
    Input("country_selector", "value"),
    Input("year_slider", "value"),
    Input("metric_selector", "value")
)
def generate_insights(countries, year_range, metric):
    try:
        if not countries or not year_range:
            raise PreventUpdate
        data = df[(df["Country"].isin(countries)) & 
                  (df["Year"] >= year_range[0]) & 
                  (df["Year"] <= year_range[1])]
        
        # Calculate insights
        insights = []
        
        # GDP Growth Rate
        gdp_data = data[["Country", "Year", "GDP_per_capita"]]
        gdp_growth = gdp_data.groupby("Country").apply(
            lambda x: x.sort_values("Year").iloc[-1]["GDP_per_capita"] / 
                      x.sort_values("Year").iloc[0]["GDP_per_capita"] - 1
        ).reset_index(name="growth_rate")
        fastest_growing = gdp_growth.loc[gdp_growth["growth_rate"].idxmax()]
        insights.append(f"Fastest growing GDP: {fastest_growing['Country']} ({fastest_growing['growth_rate']:.1%})")

        # Life Expectancy Improvement
        le_data = data[["Country", "Year", "Life_Expectancy"]]
        le_change = le_data.groupby("Country").apply(
            lambda x: x.sort_values("Year").iloc[-1]["Life_Expectancy"] - 
                      x.sort_values("Year").iloc[0]["Life_Expectancy"]
        ).reset_index(name="change")
        most_improved = le_change.loc[le_change["change"].idxmax()]
        insights.append(f"Most improved life expectancy: {most_improved['Country']} ({most_improved['change']:.1f} years)")

        # CO2 Reduction
        co2_data = data[["Country", "Year", "CO2_per_capita"]]
        co2_change = co2_data.groupby("Country").apply(
            lambda x: x.sort_values("Year").iloc[-1]["CO2_per_capita"] - 
                      x.sort_values("Year").iloc[0]["CO2_per_capita"]
        ).reset_index(name="change")
        most_reduced = co2_change.loc[co2_change["change"].idxmin()]
        insights.append(f"Most CO2 reduction: {most_reduced['Country']} ({most_reduced['change']:.1f} t per capita)")

        return html.Ul([html.Li(insight) for insight in insights])
    except Exception as e:
        print(f"Error in insights callback: {e}")
        raise PreventUpdate

@callback(
    Output("animation_interval", "disabled"),
    Input("play_pause", "n_clicks")
)
def toggle_animation(n_clicks):
    try:
        if n_clicks is None:
            raise PreventUpdate
        return not dash.callback_context.outputs_list["animation_interval.disabled"]["value"]
    except Exception as e:
        print(f"Error in toggle animation callback: {e}")
        raise PreventUpdate

# -------------------- Run --------------------
if __name__ == "__main__":
    app.run(debug=False)
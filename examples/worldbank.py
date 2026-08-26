import dash
from dash import dcc, html, Input, Output, State
import plotly.express as px
import pandas as pd
import numpy as np

# ----------------------------
# Create synthetic dataset with meaningful variables
# ----------------------------
np.random.seed(42)
years = list(range(2000, 2021))
countries = px.data.gapminder()["country"].unique()
metrics = ["GDP (per capita)", "Life Expectancy", "Population", "Education Index"]
continents = ['Africa', 'Americas', 'Asia', 'Europe', 'Oceania']

# Assign countries to continents (simplified)
country_continent = {}
for country in countries:
    if country in ['Canada', 'United States', 'Mexico', 'Brazil', 'Argentina']:
        country_continent[country] = 'Americas'
    elif country in ['China', 'India', 'Japan', 'South Korea', 'Indonesia']:
        country_continent[country] = 'Asia'
    elif country in ['Germany', 'France', 'United Kingdom', 'Italy', 'Spain']:
        country_continent[country] = 'Europe'
    elif country in ['Australia', 'New Zealand']:
        country_continent[country] = 'Oceania'
    else:
        country_continent[country] = 'Africa'

data = []
for year in years:
    for country in countries:
        continent = country_continent[country]
        base_gdp = np.random.normal(10000, 3000) * (1 + (year-2000)*0.02)
        base_life = np.random.normal(65, 10) * (1 + (year-2000)*0.003)
        
        data.append({
            "Country": country,
            "Continent": continent,
            "Year": year,
            "GDP (per capita)": max(500, base_gdp + np.random.normal(0, 500)),
            "Life Expectancy": max(40, base_life + np.random.normal(0, 2)),
            "Population": max(1000000, np.random.randint(1000000, 1000000000) * (1 + (year-2000)*0.01)),
            "Education Index": np.clip(np.random.normal(0.6, 0.15), 0.3, 1.0),
            "Primary Enrollment": np.random.randint(70, 100),
            "Internet Users (%)": np.clip(np.random.normal(30 + (year-2000)*2, 10), 0, 100)
        })

df = pd.DataFrame(data)

# ----------------------------
# App setup
# ----------------------------
app = dash.Dash(__name__)
server = app.server

# Color scales
color_scales = {
    "GDP (per capita)": px.colors.sequential.Viridis,
    "Life Expectancy": px.colors.sequential.Plasma,
    "Population": px.colors.sequential.Magma,
    "Education Index": px.colors.sequential.Tealgrn,
    "Primary Enrollment": px.colors.sequential.Bluered,
    "Internet Users (%)": px.colors.sequential.Sunset
}

# ----------------------------
# Layout
# ----------------------------
app.layout = html.Div([
    html.H1("🌍 Global Development Dashboard", style={"textAlign": "center"}),
    
    html.Div([
        html.Button("⏯ Play/Pause", id="play-button", n_clicks=0),
        dcc.Dropdown(
            id="year-dropdown",
            options=[{"label": y, "value": y} for y in years],
            value=2000,
            clearable=False,
            style={"width": "150px", "display": "inline-block", "marginLeft": "20px"}
        ),
        dcc.Dropdown(
            id="metric-dropdown",
            options=[{"label": m, "value": m} for m in metrics],
            value="GDP (per capita)",
            clearable=False,
            style={"width": "250px", "display": "inline-block", "marginLeft": "20px"}
        ),
        dcc.Dropdown(
            id="continent-dropdown",
            options=[{"label": "All Continents", "value": "All"}] + 
                    [{"label": c, "value": c} for c in continents],
            value="All",
            clearable=False,
            style={"width": "200px", "display": "inline-block", "marginLeft": "20px"}
        )
    ], style={"textAlign": "center", "marginBottom": "10px"}),
    
    dcc.Interval(id="interval", interval=1000, disabled=True),
    
    html.Div([
        dcc.Graph(id="world-map", style={"width": "60%", "display": "inline-block"}),
        dcc.Graph(id="bar-chart", style={"width": "40%", "display": "inline-block"})
    ]),
    
    html.Div([
        dcc.Graph(id="time-series", style={"height": "300px"})
    ]),
    
    html.Div(id="country-details", style={
        "padding": "15px",
        "marginTop": "10px",
        "border": "1px solid #ccc",
        "borderRadius": "10px",
        "backgroundColor": "#f9f9f9"
    })
])

# ----------------------------
# Callbacks
# ----------------------------
@app.callback(
    Output("interval", "disabled"),
    Input("play-button", "n_clicks"),
    prevent_initial_call=True
)
def toggle_play(n_clicks):
    return n_clicks % 2 == 0

@app.callback(
    Output("year-dropdown", "value"),
    Input("interval", "n_intervals"),
    State("year-dropdown", "value"),
    prevent_initial_call=True
)
def advance_year(n, current_year):
    idx = years.index(current_year)
    return years[(idx + 1) % len(years)]

@app.callback(
    Output("world-map", "figure"),
    Output("bar-chart", "figure"),
    Output("time-series", "figure"),
    Output("country-details", "children"),
    Input("year-dropdown", "value"),
    Input("metric-dropdown", "value"),
    Input("continent-dropdown", "value"),
    Input("world-map", "clickData"),
    State("year-dropdown", "value")
)
def update_dashboard(selected_year, selected_metric, selected_continent, click_data, current_year):
    # Filter data
    filtered_df = df[df["Year"] == selected_year]
    
    if selected_continent != "All":
        filtered_df = filtered_df[filtered_df["Continent"] == selected_continent]
    
    # Handle country selection from map
    selected_country = None
    if click_data:
        selected_country = click_data["points"][0]["location"]
    
    # World map
    fig_map = px.choropleth(
        filtered_df,
        locations="Country",
        locationmode="country names",
        color=selected_metric,
        hover_name="Country",
        hover_data=["Continent", "GDP (per capita)", "Life Expectancy", "Population"],
        color_continuous_scale=color_scales[selected_metric],
        projection="natural earth",
        title=f"Global {selected_metric} in {selected_year}"
    )
    
    if selected_country:
        fig_map.add_scattergeo(
            locations=[selected_country],
            locationmode="country names",
            mode="markers",
            marker=dict(size=15, color="red", symbol="star"),
            name="Selected Country"
        )
    
    fig_map.update_layout(margin={"r":0,"t":30,"l":0,"b":0})
    
    # Bar chart - top 10 for selected metric
    top_countries = filtered_df.sort_values(selected_metric, ascending=False).head(10)
    fig_bar = px.bar(
        top_countries,
        x=selected_metric,
        y="Country",
        orientation="h",
        color=selected_metric,
        color_continuous_scale=color_scales[selected_metric],
        title=f"Top 10 Countries by {selected_metric} ({selected_year})",
        hover_data=["Continent"]
    )
    fig_bar.update_layout(yaxis=dict(autorange="reversed"))
    
    # Time series for selected country or global average
    if selected_country:
        country_df = df[df["Country"] == selected_country]
        fig_ts = px.line(
            country_df,
            x="Year",
            y=metrics,
            title=f"Development Trends for {selected_country} (2000-2020)",
            markers=True
        )
    else:
        # Show continent average if continent is selected, otherwise global average
        if selected_continent != "All":
            avg_df = df[df["Continent"] == selected_continent].groupby("Year")[metrics].mean().reset_index()
            title = f"Average {selected_continent} Trends (2000-2020)"
        else:
            avg_df = df.groupby("Year")[metrics].mean().reset_index()
            title = "Global Average Trends (2000-2020)"
        
        fig_ts = px.line(
            avg_df,
            x="Year",
            y=metrics,
            title=title,
            markers=True
        )
    
    fig_ts.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    
    # Country details panel
    if selected_country:
        country_data = filtered_df[filtered_df["Country"] == selected_country].iloc[0]
        
        details = html.Div([
            html.H3(f"📊 {selected_country} Development Profile ({selected_year})"),
            html.Div([
                html.Div([
                    html.Div(f"🏙️ Continent: {country_data['Continent']}"),
                    html.Div(f"💰 GDP per capita: ${country_data['GDP (per capita)']:,.0f}"),
                    html.Div(f"🧓 Life Expectancy: {country_data['Life Expectancy']:.1f} years"),
                ], style={"width": "33%", "display": "inline-block"}),
                
                html.Div([
                    html.Div(f"👥 Population: {country_data['Population']:,.0f}"),
                    html.Div(f"🎓 Education Index: {country_data['Education Index']:.2f}/1.0"),
                    html.Div(f"📚 Primary Enrollment: {country_data['Primary Enrollment']}%"),
                ], style={"width": "33%", "display": "inline-block"}),
                
                html.Div([
                    html.Div(f"🌐 Internet Users: {country_data['Internet Users (%)']:.1f}%"),
                    html.Div(f"📈 Rank in {selected_metric}: {filtered_df[selected_metric].rank(ascending=False).loc[country_data.name]:.0f}/{len(filtered_df)}"),
                    html.Div(f"🌍 % of world population: {(country_data['Population']/filtered_df['Population'].sum()*100):.2f}%"),
                ], style={"width": "33%", "display": "inline-block"})
            ])
        ])
    else:
        details = html.Div([
            html.H3("ℹ️ Dashboard Information"),
            html.P("This dashboard tracks key development indicators across countries from 2000-2020."),
            html.P("Select a country on the map to view detailed information."),
            html.P("Use the controls above to:"),
            html.Ul([
                html.Li("Play/pause the year animation"),
                html.Li("Select a specific year"),
                html.Li("Choose which metric to visualize"),
                html.Li("Filter by continent")
            ])
        ])
    
    return fig_map, fig_bar, fig_ts, details


if __name__ == "__main__":
    app.run(debug=True)
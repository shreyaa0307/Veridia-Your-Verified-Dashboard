import dash
from dash import dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import pycountry
import pycountry_convert as pc
from dash.exceptions import PreventUpdate

import os as _os
DATA_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'backend', 'data', 'world_environment_synthetic.csv')
df = pd.read_csv(DATA_FILE)

# Handle missing values
df['GDP_per_capita'] = df['GDP_per_capita'].fillna(df['GDP_per_capita'].mean())
df['Life_Expectancy'] = df['Life_Expectancy'].fillna(df['Life_Expectancy'].mean())
df['CO2_per_capita'] = df['CO2_per_capita'].fillna(df['CO2_per_capita'].mean())

# Helper functions
def get_iso3(country_name):
    try:
        return pycountry.countries.lookup(country_name).alpha_3
    except:
        return None

def get_continent(country_name):
    try:
        country_code = pycountry.countries.lookup(country_name).alpha_2
        continent_code = pc.country_alpha2_to_continent_code(country_code)
        return pc.convert_continent_code_to_continent_name(continent_code)
    except:
        return 'Other'

# Preprocess data
df['iso_alpha'] = df['Country'].apply(get_iso3)
df['continent'] = df['Country'].apply(get_continent)
df['pop_size'] = np.log10(df['Population']) * 5  # Reduced multiplier for better visualization

# App initialization
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True
)
app.title = "Global Development & Sustainability Dashboard"

# Layout components
controls = dbc.Card(
    [
        dbc.CardBody(
            [
                html.H4("Controls", className="card-title"),
                html.Label('Select Country(ies)'),
                dcc.Dropdown(
                    id='country-selector',
                    options=[{'label': c, 'value': c} for c in sorted(df['Country'].unique())],
                    value=['United States'],  # Changed to list for multi-select
                    multi=True,
                    placeholder='Select Countries'
                ),
                html.Br(),
                html.Label('Year Range'),
                dcc.RangeSlider(
                    id='year-range',
                    min=df['Year'].min(),
                    max=df['Year'].max(),
                    value=[df['Year'].min(), df['Year'].max()],
                    marks={str(year): str(year) for year in range(df['Year'].min(), df['Year'].max()+1, 5)},
                    step=1
                ),
                html.Br(),
                html.Label('Metric for Map'),
                dcc.Dropdown(
                    id='metric-selector',
                    options=[
                        {'label': 'GDP per Capita', 'value': 'GDP_per_capita'},
                        {'label': 'Life Expectancy', 'value': 'Life_Expectancy'},
                        {'label': 'CO₂ per Capita', 'value': 'CO2_per_capita'},
                        {'label': 'Population', 'value': 'Population'}
                    ],
                    value='GDP_per_capita'
                ),
                html.Br(),
                dbc.Button('Play/Pause Animation', id='play-pause-button', color='primary'),
                dcc.Interval(id='interval-component', interval=1000, disabled=True),
                html.Br(),
                dcc.Checklist(
                    id='continent-legend',
                    options=[{'label': 'Show Continent Legend', 'value': 'Show'}],
                    value=['Show']
                )
            ]
        )
    ],
    style={"height": "100%"}
)

# Graph components
map_graph = dcc.Graph(id='map-graph', style={'height': '500px'})
line_graph = dcc.Graph(id='line-graph', style={'height': '400px'})
scatter_graph = dcc.Graph(id='scatter-graph', style={'height': '400px'})
data_table = dash_table.DataTable(
    id='data-table',
    columns=[{'name': col, 'id': col} for col in df.columns],
    page_size=10,
    style_table={'overflowX': 'auto'},
    style_cell={
        'textAlign': 'left',
        'backgroundColor': '#1a1a1a',
        'color': 'white'
    },
    style_header={
        'fontWeight': 'bold',
        'backgroundColor': '#2a2a2a'
    },
    filter_action='native',
    sort_action='native',
    export_format='csv'
)

insights_panel = dbc.Card(
    [
        dbc.CardBody(
            [
                html.H4("Key Insights", className="card-title"),
                html.Div(id='insights-panel')
            ]
        )
    ],
    style={"margin-top": "20px"}
)

# Layout
app.layout = dbc.Container(
    fluid=True,
    children=[
        html.H1("Global Development & Sustainability Dashboard", 
                style={'color': '#ffffff', 'textAlign': 'center', 'padding': '20px 0'}),
        dbc.Row([
            dbc.Col(controls, width=3),
            dbc.Col(map_graph, width=9)
        ], style={'margin-bottom': '20px'}),
        dbc.Row([
            dbc.Col(line_graph, width=6),
            dbc.Col(scatter_graph, width=6)
        ], style={'margin-bottom': '20px'}),
        dbc.Row([
            dbc.Col(data_table, width=12)
        ], style={'margin-bottom': '20px'}),
        dbc.Row([
            dbc.Col(insights_panel, width=12)
        ]),
        dcc.Store(id='filtered-data-store')
    ],
    style={
        'background': '#1a1a1a',
        'color': '#ffffff',
        'fontFamily': 'Helvetica Neue, Arial, sans-serif',
        'padding': '20px'
    }
)

# Callbacks
@app.callback(
    Output('filtered-data-store', 'data'),
    Input('country-selector', 'value'),
    Input('year-range', 'value'),
    prevent_initial_call=True
)
def update_filtered_data(countries, year_range):
    if not countries or not year_range:
        raise PreventUpdate
        
    filtered_df = df[
        (df['Country'].isin(countries)) & 
        (df['Year'] >= year_range[0]) & 
        (df['Year'] <= year_range[1])
    ]
    return filtered_df.to_dict('records')

@app.callback(
    Output('map-graph', 'figure'),
    Input('filtered-data-store', 'data'),
    Input('metric-selector', 'value')
)
def update_map(filtered_data, metric):
    if not filtered_data:
        raise PreventUpdate
        
    filtered_df = pd.DataFrame(filtered_data)
    
    fig = px.choropleth(
        filtered_df,
        locations="iso_alpha",
        color=metric,
        hover_name="Country",
        hover_data=["Year", "continent", "Population"],
        color_continuous_scale=px.colors.sequential.Plasma,
        title=f"{metric.replace('_', ' ')} by Country",
        projection="natural earth"
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=50, b=0),
        plot_bgcolor='#1a1a1a',
        paper_bgcolor='#1a1a1a',
        font_color='white'
    )
    return fig

@app.callback(
    Output('line-graph', 'figure'),
    Input('filtered-data-store', 'data')
)
def update_line(filtered_data):
    if not filtered_data:
        raise PreventUpdate
        
    filtered_df = pd.DataFrame(filtered_data)
    
    fig = go.Figure()
    
    for country in filtered_df['Country'].unique():
        country_df = filtered_df[filtered_df['Country'] == country]
        fig.add_trace(go.Scatter(
            x=country_df['Year'],
            y=country_df['Life_Expectancy'],
            mode='lines+markers',
            name=f"{country} Life Expectancy",
            line=dict(width=2)
        ))
    
    fig.update_layout(
        title="Life Expectancy Over Time",
        xaxis_title="Year",
        yaxis_title="Life Expectancy (years)",
        plot_bgcolor='#1a1a1a',
        paper_bgcolor='#1a1a1a',
        font_color='white',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    return fig

@app.callback(
    Output('scatter-graph', 'figure'),
    Input('filtered-data-store', 'data'),
    Input('continent-legend', 'value')
)
def update_scatter(filtered_data, legend_state):
    if not filtered_data:
        raise PreventUpdate
        
    filtered_df = pd.DataFrame(filtered_data)
    show_legend = 'Show' in legend_state
    
    color_map = {
        'Africa': '#FF0000',
        'Asia': '#00FF00',
        'Europe': '#0000FF',
        'North America': '#FFFF00',
        'Oceania': '#FF00FF',
        'South America': '#00FFFF',
        'Other': '#888888'
    }
    
    fig = px.scatter(
        filtered_df,
        x='GDP_per_capita',
        y='Life_Expectancy',
        size='pop_size',
        color='continent',
        color_discrete_map=color_map,
        hover_name='Country',
        hover_data=['Year', 'CO2_per_capita'],
        title="GDP vs Life Expectancy",
        size_max=20
    )
    
    fig.update_layout(
        plot_bgcolor='#1a1a1a',
        paper_bgcolor='#1a1a1a',
        font_color='white',
        showlegend=show_legend
    )
    
    return fig

@app.callback(
    Output('data-table', 'data'),
    Input('filtered-data-store', 'data')
)
def update_table(filtered_data):
    if not filtered_data:
        raise PreventUpdate
    return filtered_data

@app.callback(
    Output('insights-panel', 'children'),
    Input('filtered-data-store', 'data'),
    Input('metric-selector', 'value')
)
def update_insights(filtered_data, metric):
    if not filtered_data:
        raise PreventUpdate
        
    filtered_df = pd.DataFrame(filtered_data)
    
    insights = [
        f"Average {metric.replace('_', ' ')}: {filtered_df[metric].mean():.2f}",
        f"Maximum {metric.replace('_', ' ')}: {filtered_df[metric].max():.2f} (in {filtered_df.loc[filtered_df[metric].idxmax(), 'Country']})",
        f"Minimum {metric.replace('_', ' ')}: {filtered_df[metric].min():.2f} (in {filtered_df.loc[filtered_df[metric].idxmin(), 'Country']})",
        f"Number of countries: {len(filtered_df['Country'].unique())}",
        f"Time period: {filtered_df['Year'].min()} to {filtered_df['Year'].max()}"
    ]
    
    return html.Ul([html.Li(insight) for insight in insights])

@app.callback(
    Output('interval-component', 'disabled'),
    Input('play-pause-button', 'n_clicks'),
    State('interval-component', 'disabled'),
    prevent_initial_call=True
)
def toggle_animation(n_clicks, disabled):
    if n_clicks is None:
        raise PreventUpdate
    return not disabled

@app.callback(
    Output('year-range', 'value'),
    Input('interval-component', 'n_intervals'),
    State('year-range', 'value'),
    State('year-range', 'min'),
    State('year-range', 'max'),
    prevent_initial_call=True
)
def update_year_range(n_intervals, current_range, min_year, max_year):
    if current_range[1] >= max_year:
        return [min_year, min_year]
    return [current_range[0], current_range[1] + 1]

if __name__ == '__main__':
    app.run(debug=True)
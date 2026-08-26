import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime

# Generate synthetic environmental data
np.random.seed(42)
years = list(range(1990, 2023))
cities = ['New York', 'London', 'Tokyo', 'Delhi', 'São Paulo']
regions = ['North America', 'Europe', 'Asia', 'South America']

# Climate Data
temp_data = []
for year in years:
    base_temp = 0.5 + (year-1990)*0.02  # Warming trend
    for city in cities:
        temp_data.append({
            'Year': year,
            'City': city,
            'Region': regions[cities.index(city)%4],
            'Temp_Anomaly': base_temp + np.random.normal(0, 0.3),
            'CO2': 300 + (year-1990)*5 + np.random.randint(-10,10),
            'Sea_Level': (year-1990)*0.3 + np.random.normal(0,0.2)
        })
df = pd.DataFrame(temp_data)

# Wildlife Data
species = ['Polar Bears', 'Bees', 'Tigers', 'Sea Turtles']
wildlife = pd.DataFrame({
    'Year': years*4,
    'Species': np.repeat(species, len(years)),
    'Count': [10000 - (y-1990)*120 + np.random.randint(-200,200) for y in years]*2 + 
             [5000 - (y-1990)*80 + np.random.randint(-100,100) for y in years]*2
})

# ===== DASH APP =====
app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("🌍 Climate Pulse", style={'textAlign': 'center', 'color': '#2E8B57'}),
    
    html.Div([
        dcc.Dropdown(
            id='region-selector',
            options=[{'label': r, 'value': r} for r in ['All'] + regions],
            value='All',
            style={'width': '200px'}
        ),
        dcc.RangeSlider(
            id='year-slider',
            min=1990,
            max=2022,
            value=[2010, 2022],
            marks={y: str(y) for y in range(1990, 2023, 5)}
        )
    ], style={'padding': '20px', 'backgroundColor': '#F0FFF0'}),
    
    html.Div([
        dcc.Graph(id='climate-spiral'),
        dcc.Graph(id='co2-heatmap')
    ], style={'display': 'flex'}),
    
    html.Div([
        dcc.Graph(id='wildlife-trends'),
        dcc.Graph(id='sea-level-map')
    ], style={'display': 'flex'}),
    
    html.Div(id='story-card', style={
        'padding': '20px',
        'margin': '10px',
        'borderRadius': '10px',
        'backgroundColor': '#E6F7FF',
        'border': '1px solid #B0E0E6'
    })
])

# ===== CALLBACKS =====
@app.callback(
    [Output('climate-spiral', 'figure'),
     Output('co2-heatmap', 'figure'),
     Output('wildlife-trends', 'figure'),
     Output('sea-level-map', 'figure'),
     Output('story-card', 'children')],
    [Input('region-selector', 'value'),
     Input('year-slider', 'value')]
)
def update_plots(region, years):
    filtered = df[(df['Year'] >= years[0]) & (df['Year'] <= years[1])]
    if region != 'All':
        filtered = filtered[filtered['Region'] == region]
    
    # 1. Climate Spiral (Animated)
    spiral = px.line_polar(
        filtered.groupby(['Year', 'Region'])['Temp_Anomaly'].mean().reset_index(),
        r='Temp_Anomaly', theta='Year', color='Region',
        line_close=True, template='plotly_dark',
        title='Temperature Anomaly Spiral'
    )
    spiral.update_traces(fill='toself')
    
    # 2. CO2 Heatmap
    heatmap = px.density_heatmap(
        filtered, x='Year', y='City', z='CO2',
        title='CO2 Emissions Heatmap',
        color_continuous_scale='YlOrRd'
    )
    
    # 3. Wildlife Trends
    wildlife_filtered = wildlife[(wildlife['Year'] >= years[0]) & (wildlife['Year'] <= years[1])]
    trends = px.line(
        wildlife_filtered, x='Year', y='Count', color='Species',
        title='Wildlife Population Trends',
        line_shape='spline'
    )
    
    # 4. Sea Level Map
    sea_map = px.scatter_geo(
        filtered.groupby('City').last().reset_index(),
        locations='City', locationmode='country names',
        size='Sea_Level', color='Temp_Anomaly',
        title='Sea Level Rise vs Temperature',
        hover_name='City',
        color_continuous_scale='Tealrose'
    )
    
    # Story Card
    max_temp = filtered['Temp_Anomaly'].max()
    min_wildlife = wildlife_filtered['Count'].min()
    story = [
        html.H3("🌱 Environmental Insights"),
        html.P(f"🔥 Highest temp anomaly: +{max_temp:.1f}°C ({filtered.loc[filtered['Temp_Anomaly'].idxmax()]['City']})"),
        html.P(f"🦉 Most endangered: {wildlife_filtered.loc[wildlife_filtered['Count'].idxmin()]['Species']} ({min_wildlife} remaining)"),
        html.P(f"📈 CO2 increased by {(filtered['CO2'].iloc[-1] - filtered['CO2'].iloc[0]):.0f} ppm in this period"),
        html.P("💡 Prediction: " + predict_trends(filtered))
    ]
    
    return spiral, heatmap, trends, sea_map, story

def predict_trends(data):
    temp_slope = (data['Temp_Anomaly'].iloc[-1] - data['Temp_Anomaly'].iloc[0])/len(data)
    if temp_slope > 0.02:
        return "Rapid warming trend detected. Expect more extreme weather events."
    else:
        return "Moderate climate changes. Focus on conservation efforts."

if __name__ == '__main__':
    app.run(debug=True)
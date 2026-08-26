import dash
from dash import dcc, html, Input, Output, State
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

_DATA_FILE = Path(__file__).resolve().parent.parent / "backend" / "data" / "synthetic_medical_data.csv"
df = pd.read_csv(_DATA_FILE)

app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css'])
app.layout = html.Div([
    html.Div([
        html.H1("🏥 Advanced Hospital Analytics", 
               style={'textAlign': 'center', 'color': 'white', 'marginBottom': '20px'}),
        
        html.Div([
            dcc.Dropdown(
                id='hospital-selector',
                options=[{'label': h, 'value': h} for h in hospitals],
                value=['Metro General'],
                multi=True,
                style={'width': '30%'}
            ),
            dcc.Dropdown(
                id='condition-selector',
                options=[{'label': c, 'value': c} for c in conditions],
                value=conditions,
                multi=True,
                style={'width': '30%', 'marginLeft': '20px'}
            ),
            html.Button('▶ Play', id='play-button', 
                      style={'marginLeft': '20px', 'backgroundColor': '#4CAF50', 'color': 'white'})
        ], style={
            'display': 'flex', 
            'justifyContent': 'center', 
            'padding': '20px',
            'backgroundColor': '#2c3e50',
            'borderRadius': '10px'
        }),
        
        dcc.Interval(id='animate-interval', interval=1000, disabled=True),
        dcc.Store(id='filtered-data')
    ], style={'backgroundColor': '#f8f9fa', 'padding': '20px'}),
    
    html.Div([
        html.Div([
            dcc.Graph(id='admissions-heatmap')
        ], className="six columns"),
        
        html.Div([
            dcc.Graph(id='mortality-trend')
        ], className="six columns")
    ], className="row"),
    
    html.Div([
        html.Div([
            dcc.Graph(id='icu-utilization')
        ], className="six columns"),
        
        html.Div([
            dcc.Graph(id='cost-bubble')
        ], className="six columns")
    ], className="row"),
    
    html.Div(id='insight-card', style={
        'padding': '20px',
        'marginTop': '20px',
        'backgroundColor': 'white',
        'borderRadius': '10px',
        'boxShadow': '0 4px 6px 0 rgba(0, 0, 0, 0.1)'
    })
])
@app.callback(
    Output('animate-interval', 'disabled'),
    Input('play-button', 'n_clicks'),
    State('animate-interval', 'disabled'),
    prevent_initial_call=True
)
def toggle_animation(n_clicks, is_disabled):
    if n_clicks % 2 == 1:
        return False
    return True

@app.callback(
    Output('filtered-data', 'data'),
    [Input('hospital-selector', 'value'),
     Input('condition-selector', 'value')]
)
def filter_data(selected_hospitals, selected_conditions):
    filtered = df[
        (df['Hospital'].isin(selected_hospitals)) & 
        (df['Condition'].isin(selected_conditions))
    ]
    return filtered.to_json(date_format='iso', orient='split')

@app.callback(
    [Output('admissions-heatmap', 'figure'),
     Output('mortality-trend', 'figure'),
     Output('icu-utilization', 'figure'),
     Output('cost-bubble', 'figure'),
     Output('insight-card', 'children')],
    [Input('filtered-data', 'data'),
     Input('animate-interval', 'n_intervals')],
    [State('hospital-selector', 'value'),
     State('condition-selector', 'value')]
)
def update_dashboard(data, n_intervals, selected_hospitals, selected_conditions):
    filtered = pd.read_json(data, orient='split')
    
    # Determine current year for animation
    years = sorted(filtered['Year'].unique())
    current_year = years[n_intervals % len(years)] if n_intervals else years[-1]
    year_filtered = filtered[filtered['Year'] == current_year]
    
    # 1. Admissions Heatmap
    heatmap = px.density_heatmap(
        year_filtered,
        x='Month', y='Condition', z='Admissions',
        facet_col='Hospital',
        title=f'Hospital Admissions {current_year}',
        color_continuous_scale='Viridis',
        category_orders={'Month': ['January', 'February', 'March', 'April', 'May', 'June',
                                 'July', 'August', 'September', 'October', 'November', 'December']}
    )
    
    # 2. Mortality Trend
    mortality = filtered.groupby(['Year', 'Condition'])['Deaths'].sum().reset_index()
    trend = px.line(
        mortality,
        x='Year', y='Deaths', color='Condition',
        title='Mortality Trends Over Time',
        line_shape='spline'
    )
    trend.update_traces(mode='lines+markers')
    
    # 3. ICU Utilization
    icu = filtered.groupby(['Date', 'Hospital'])['ICU_Usage'].mean().reset_index()
    utilization = px.area(
        icu,
        x='Date', y='ICU_Usage', color='Hospital',
        title='ICU Utilization Over Time',
        color_discrete_sequence=px.colors.qualitative.Pastel
    )
    
    # 4. Cost Bubble Chart
    cost = filtered.groupby(['Condition', 'Hospital']).agg({
        'Cost_Per_Case': 'mean',
        'Admissions': 'sum'
    }).reset_index()
    bubble = px.scatter(
        cost,
        x='Condition', y='Cost_Per_Case', size='Admissions',
        color='Hospital', hover_name='Hospital',
        title='Treatment Costs vs Volume',
        size_max=60
    )
    
    # Insight Card
    insights = [
        html.H3(f"💡 Key Insights - {current_year}"),
        html.P(f"🏥 Highest Admissions: {year_filtered.groupby('Hospital')['Admissions'].sum().idxmax()}"),
        html.P(f"⚠️ Critical Condition: {year_filtered.groupby('Condition')['Deaths'].sum().idxmax()}"),
        html.P(f"💰 Most Costly: {cost.loc[cost['Cost_Per_Case'].idxmax()]['Condition']} " +
              f"(${cost['Cost_Per_Case'].max():,.0f}/case)"),
        html.P("🔍 Recommendation: " + generate_insights(year_filtered))
    ]
    return heatmap, trend, utilization, bubble, insights
def generate_insights(data):
    avg_mortality = data['Deaths'].sum() / data['Admissions'].sum()
    if avg_mortality > 0.15:
        return "High mortality rates detected. Review treatment protocols immediately."
    elif data['ICU_Usage'].mean() > 0.25:
        return "ICU capacity strained. Consider expanding critical care resources."
    else:
        return "Operations within normal parameters. Monitor for emerging trends."
if __name__ == '__main__':
    app.run(debug=True, port=8051)
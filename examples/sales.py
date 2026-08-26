import dash
from dash import dcc, html, Input, Output, State  # Added State here
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime

np.random.seed(42)
years = [2021, 2022, 2023]
products = ['Laptops', 'Phones', 'Tablets', 'Accessories']
customers = ['Amazon', 'Walmart', 'Best Buy', 'Target', 'Local Stores']

data = []
for year in years:
    for month in range(1, 13):
        for product in products:
            for customer in customers:
                units = np.random.randint(10, 500)
                unit_price = np.random.uniform(100, 2000)
                cost = unit_price * 0.7  # 30% profit margin
                
                data.append({
                    'Date': datetime(year, month, 1),
                    'Year': year,
                    'Month': month,
                    'Product': product,
                    'Customer': customer,
                    'Units_Sold': units,
                    'Revenue': units * unit_price,
                    'Profit': units * (unit_price - cost)
                })

df = pd.DataFrame(data)
df['Month_Name'] = df['Date'].dt.strftime('%b')

# ======================
# Dash App
# ======================
app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("📊 Sales Dashboard", style={'textAlign': 'center'}),
    
    # Controls
    html.Div([
        dcc.Dropdown(
            id='year-selector',
            options=[{'label': y, 'value': y} for y in years],
            value=2023,
            clearable=False,
            style={'width': '150px'}
        ),
        dcc.Dropdown(
            id='customer-selector',
            options=[{'label': 'All Customers', 'value': 'All'}] + 
                    [{'label': c, 'value': c} for c in customers],
            value='All',
            style={'width': '200px', 'marginLeft': '20px'}
        ),
        html.Button('▶ Play Animation', id='play-button', style={'marginLeft': '20px'})
    ], style={'display': 'flex', 'justifyContent': 'center', 'padding': '20px'}),
    
    dcc.Interval(id='animate-interval', interval=1000, disabled=True),
    
    # Main Visualizations
    html.Div([
        dcc.Graph(id='monthly-profit-chart', style={'width': '50%', 'display': 'inline-block'}),
        dcc.Graph(id='product-sales-chart', style={'width': '50%', 'display': 'inline-block'})
    ]),
    
    html.Div([
        dcc.Graph(id='customer-trends-chart')
    ]),
    
    # Story Card
    html.Div(id='story-card', style={
        'padding': '20px',
        'marginTop': '20px',
        'borderRadius': '10px',
        'backgroundColor': '#f8f9fa',
        'border': '1px solid #ddd'
    })
])

# ======================
# Callbacks
# ======================
@app.callback(
    Output('animate-interval', 'disabled'),
    Input('play-button', 'n_clicks'),
    prevent_initial_call=True
)
def toggle_animation(n_clicks):
    return n_clicks % 2 == 0

@app.callback(
    Output('year-selector', 'value'),
    Input('animate-interval', 'n_intervals'),
    State('year-selector', 'value')
)
def update_year(n, current_year):
    idx = years.index(current_year)
    return years[(idx + 1) % len(years)]

@app.callback(
    [Output('monthly-profit-chart', 'figure'),
     Output('product-sales-chart', 'figure'),
     Output('customer-trends-chart', 'figure'),
     Output('story-card', 'children')],
    [Input('year-selector', 'value'),
     Input('customer-selector', 'value')]
)
def update_charts(selected_year, selected_customer):
    # Filter data
    filtered = df[df['Year'] == selected_year]
    if selected_customer != 'All':
        filtered = filtered[filtered['Customer'] == selected_customer]
    
    # 1. Monthly Profit Chart (Animated Bars)
    monthly = filtered.groupby(['Month', 'Month_Name'])['Profit'].sum().reset_index()
    fig1 = px.bar(
        monthly, x='Month_Name', y='Profit',
        title=f'Monthly Profit - {selected_year}',
        color='Profit',
        color_continuous_scale='Teal'
    )
    fig1.update_layout(xaxis={'categoryorder': 'array', 'categoryarray': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                                                                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']})
    
    # 2. Product Sales (Pie + Donut)
    product_sales = filtered.groupby('Product')['Units_Sold'].sum().reset_index()
    fig2 = px.pie(
        product_sales, values='Units_Sold', names='Product',
        title=f'Product Sales Distribution - {selected_year}',
        hole=0.4
    )
    
    # 3. Customer Trends (Line Chart)
    customer_trends = filtered.groupby(['Month', 'Customer'])['Revenue'].sum().reset_index()
    fig3 = px.line(
        customer_trends, x='Month', y='Revenue', color='Customer',
        title='Monthly Revenue by Customer',
        markers=True
    )
    
    # Story Card Content
    best_month = monthly.loc[monthly['Profit'].idxmax()]
    best_product = product_sales.loc[product_sales['Units_Sold'].idxmax()]
    
    story = [
        html.H3(f"📈 Insights for {selected_year}"),
        html.P(f"💰 Best Month: {best_month['Month_Name']} (Profit: ${best_month['Profit']:,.0f})"),
        html.P(f"🏆 Top Product: {best_product['Product']} (Sold: {best_product['Units_Sold']} units)"),
        html.P(f"📅 Yearly Profit: ${filtered['Profit'].sum():,.0f}"),
        html.P("💡 Recommendation: " + get_recommendation(filtered))
    ]
    
    return fig1, fig2, fig3, story

def get_recommendation(data):
    avg_profit = data['Profit'].mean()
    if avg_profit > 50000:
        return "Strong performance! Consider expanding inventory for top products."
    elif avg_profit > 30000:
        return "Steady growth. Focus on customer retention strategies."
    else:
        return "Review pricing strategy and explore new customer segments."

# ======================
# Run App
# ======================
if __name__ == '__main__':
    app.run(debug=True)
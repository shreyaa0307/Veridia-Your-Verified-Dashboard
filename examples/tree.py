# ml_tree_cytoscape.py
import dash
from dash import dcc, html, Input, Output, State
import dash_cytoscape as cyto
import plotly.express as px
import plotly.graph_objects as go
from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import confusion_matrix
import pandas as pd
import numpy as np
import math
import threading, time

# ---- Data ----
data = load_breast_cancer()
X = pd.DataFrame(data.data, columns=data.feature_names)
y = data.target
feature_names = X.columns.tolist()

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)

# Fit an initial tree to get pruning path
base = DecisionTreeClassifier(random_state=0)
base.fit(X_train, y_train)
path = base.cost_complexity_pruning_path(X_train, y_train)
alphas = np.unique(np.clip(path.ccp_alphas, 0.0, 0.05))  # restrict range
# keep a reasonable number of alphas
if len(alphas) > 30:
    alphas = np.linspace(alphas.min(), alphas.max(), 28)

# ---- Helpers: convert sklearn tree to cytoscape elements with layout ----
from sklearn.tree import _tree
def tree_to_dict(clf):
    T = clf.tree_
    feature = T.feature
    threshold = T.threshold
    value = T.value
    children_left = T.children_left
    children_right = T.children_right
    node_count = T.node_count
    # build dict nodes
    nodes = {}
    def build(i, depth=0, pos_index=[0]):
        nid = i
        if children_left[i] == _tree.TREE_LEAF:
            x = pos_index[0]
            pos_index[0] += 1
        else:
            build(children_left[i], depth+1, pos_index)
            build(children_right[i], depth+1, pos_index)
            x = ( (nodes[children_left[i]]['x']) + (nodes[children_right[i]]['x']) ) / 2.0
        y = -depth  # y goes down with depth
        if feature[i] >= 0:
            label = f"{feature_names[feature[i]]} ≤ {threshold[i]:.2f}"
        else:
            # leaf: show class counts
            counts = value[i][0]
            cls = np.argmax(counts)
            label = f"leaf: class={data.target_names[cls]}\\n{counts.astype(int)}"
        nodes[i] = {"id": str(i), "label": label, "x": x, "y": y}
    build(0)
    # elements: nodes + edges
    elements = []
    for i, nd in nodes.items():
        elements.append({
            "data": {"id": nd["id"], "label": nd["label"]},
            "position": {"x": nd["x"]*200, "y": nd["y"]*140},
            "selectable": True
        })
    for i in range(node_count):
        if children_left[i] != _tree.TREE_LEAF:
            elements.append({"data": {"source": str(i), "target": str(children_left[i])}})
            elements.append({"data": {"source": str(i), "target": str(children_right[i])}})
    return elements

# ---- Model + plotting helpers ----
def fit_and_metrics(max_depth, min_samples_split, ccp_alpha):
    clf = DecisionTreeClassifier(max_depth=max_depth,
                                 min_samples_split=int(min_samples_split),
                                 ccp_alpha=ccp_alpha, random_state=42)
    clf.fit(X_train, y_train)
    train_err = 1 - clf.score(X_train, y_train)
    test_err = 1 - clf.score(X_test, y_test)
    y_pred = clf.predict(X_test)
    cm = confusion_matrix(y_test, y_pred)
    fi = pd.Series(clf.feature_importances_, index=feature_names).sort_values(ascending=False)
    elements = tree_to_dict(clf)
    return {"clf": clf, "train_err": train_err, "test_err": test_err, "cm": cm, "fi": fi, "elements": elements}

# precompute errors along pruning alphas for the curve (using a fixed default depth)
def compute_prune_curve(max_depth=6, min_samples_split=2):
    train_errs, test_errs = [], []
    al = alphas
    for a in al:
        out = fit_and_metrics(max_depth, min_samples_split, a)
        train_errs.append(out["train_err"])
        test_errs.append(out["test_err"])
    return al, np.array(train_errs), np.array(test_errs)

# initial computation
pr_alphas, pr_train, pr_test = compute_prune_curve(max_depth=6)

# ---- Dash app ----
app = dash.Dash(__name__)
app.layout = html.Div([
    html.H2("Interactive ML Pruning Explorer — Decision Tree"),
    html.Div([
        html.Div([
            html.Label("Max depth"), dcc.Slider(1, 12, 1, value=6, id="max_depth"),
            html.Label("Min samples split"), dcc.Slider(2, 50, 1, value=2, id="min_samples_split"),
            html.Label("ccp_alpha (pruning)"), 
            dcc.Slider(0, len(pr_alphas)-1, 1, value=0, id="alpha_index",
                       marks={i: f"{pr_alphas[i]:.4f}" for i in range(0, len(pr_alphas), max(1, len(pr_alphas)//8))}),
            html.Div(style={"marginTop":"6px"}, children=[
                html.Button("Play", id="play-button", n_clicks=0),
                html.Button("Pause", id="pause-button", n_clicks=0)
            ]),
            html.Div(id="model-stats", style={"marginTop":"10px","fontSize":"13px","whiteSpace":"pre-line"})
        ], style={"width":"22%","display":"inline-block","verticalAlign":"top","padding":"10px","border":"1px solid #eee","borderRadius":"6px"}),

        html.Div([
            dcc.Graph(id="prune-curve", config={"displayModeBar":False}, style={"height":"300px"}),
            html.Div([
                dcc.Graph(id="feature-imp", style={"width":"49%","display":"inline-block"}),
                dcc.Graph(id="confmat", style={"width":"49%","display":"inline-block"})
            ])
        ], style={"width":"38%","display":"inline-block","paddingLeft":"12px","verticalAlign":"top"}),

        html.Div([
            cyto.Cytoscape(
                id='tree-graph',
                layout={'name': 'preset'},
                style={'width': '100%', 'height': '640px'},
                elements=[],  # filled by callback
                stylesheet=[
                    {'selector': 'node', 'style': {'label': 'data(label)', 'text-wrap': 'wrap', 'text-valign':'center',
                                                   'background-color': '#FFCC99', 'width': '60px','height':'40px','font-size':'11px'}},
                    {'selector': 'edge', 'style': {'curve-style': 'bezier','target-arrow-shape':'vee','line-color':'#888'}}
                ],
                userZoomingEnabled=True,
                userPanningEnabled=True
            )
        ], style={"width":"38%","display":"inline-block","verticalAlign":"top","paddingLeft":"12px"})
    ], style={"display":"flex","gap":"12px"})
], style={"fontFamily":"Arial, Helvetica, sans-serif","padding":"8px"})

# ---- Callbacks ----
@app.callback(
    Output("prune-curve", "figure"),
    Output("feature-imp", "figure"),
    Output("confmat", "figure"),
    Output("tree-graph", "elements"),
    Output("model-stats", "children"),
    Input("max_depth", "value"),
    Input("min_samples_split", "value"),
    Input("alpha_index", "value")
)
def update_all(max_depth, min_samples_split, alpha_index):
    ai = int(alpha_index)
    a = pr_alphas[ai]
    out = fit_and_metrics(max_depth, min_samples_split, a)
    # prune/error curve figure with vertical selector line
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pr_alphas, y=pr_train, mode="lines+markers", name="train error"))
    fig.add_trace(go.Scatter(x=pr_alphas, y=pr_test, mode="lines+markers", name="test error"))
    fig.add_vline(x=a, line_dash="dash", line_color="black")
    fig.update_layout(title="Pruning path: error vs ccp_alpha", xaxis_title="ccp_alpha", yaxis_title="Error rate")

    # feature importance top 10
    fi = out["fi"].head(10)
    fig_fi = px.bar(fi[::-1], x=fi[::-1].values, y=fi[::-1].index, orientation="h", labels={'x':'importance','y':''}, title="Top feature importances")

    # confusion matrix
    cm = out["cm"]
    fig_cm = px.imshow(cm, text_auto=True, color_continuous_scale="Blues", title="Confusion matrix")
    fig_cm.update_xaxes(title="Pred")
    fig_cm.update_yaxes(title="True")

    # cytoscape elements (tree)
    elements = out["elements"]
    # the 'position' keys already set in element dicts from tree_to_dict -> Cytoscape will use 'preset' layout
    # model stats summary
    stats = f"ccp_alpha: {a:.5f}\ntrain error: {out['train_err']:.3f}\ntest error: {out['test_err']:.3f}\nnodes: {len([e for e in elements if 'position' in e])}"
    return fig, fig_fi, fig_cm, elements, stats

# Play/Pause animation: increment alpha_index at interval while playing
app.clientside_callback(
    """
    function(n_clicks_play, n_clicks_pause, current_index, n_intervals, max_index) {
        // This clientside callback returns a dict controlling whether the animation runs and the current index.
        // We keep it simple: return current_index unchanged; server handles index via the interval.
        return window.dash_clientside.no_update;
    }
    """,
    Output("model-stats","children"),
    Input("play-button","n_clicks"),
    Input("pause-button","n_clicks"),
    State("alpha_index","value"),
    Input("prune-curve","clickData"),
    State("alpha_index","value")
)

# Lightweight server-side interval control:
app.layout.children.append(dcc.Interval(id="anim-interval", interval=700, n_intervals=0, disabled=True))

@app.callback(
    Output("anim-interval", "disabled"),
    Input("play-button", "n_clicks"),
    Input("pause-button", "n_clicks"),
    State("anim-interval", "disabled"),
    prevent_initial_call=True
)
def play_pause(play, pause, disabled):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    prop = ctx.triggered[0]['prop_id'].split('.')[0]
    if prop == "play-button":
        return False
    else:
        return True

@app.callback(
    Output("alpha_index", "value"),
    Input("anim-interval", "n_intervals"),
    State("alpha_index", "value"),
    prevent_initial_call=True
)
def advance_alpha(n, current):
    if current is None:
        return 0
    nxt = int(current) + 1
    if nxt >= len(pr_alphas):
        nxt = 0
    return nxt

# ---- Run ----
if __name__ == "__main__":
    app.run(debug=True)
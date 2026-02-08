"""
generate_chart.py — Generate interactive PA Break chart HTML
Standalone script, no notebook dependency needed.
"""
import sys
sys.path.insert(0, '.')

from fetch_data import fetch_ohlcv
from strategy_pa_break import run_pa_break, print_backtest_summary
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

# ====================== CONFIG ======================
SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
BARS = 500
PIVOT_LEN = 5
RR_RATIO = 2.0
IMPULSE_MULT = 1.5
BREAK_MULT = 0.25

# ====================== FETCH DATA ======================
df = fetch_ohlcv(SYMBOL, TIMEFRAME, BARS)
signals, swings = run_pa_break(df, pivot_len=PIVOT_LEN, rr_ratio=RR_RATIO, impulse_mult=IMPULSE_MULT, break_mult=BREAK_MULT)

print(f"\n📊 Strategy: PA Break v0.7.0 — Wave Confirm + Retest")
print(f"   Symbol: {SYMBOL} | TF: {TIMEFRAME} | Bars: {len(df)}")
print(f"   PivotLen={PIVOT_LEN} | RR={RR_RATIO} | ImpulseMult={IMPULSE_MULT} | BreakMult={BREAK_MULT}")
print_backtest_summary(signals)

# ====================== BUILD CHART ======================
fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                    vertical_spacing=0.03,
                    row_heights=[0.85, 0.15])

# Candlestick
fig.add_trace(go.Candlestick(
    x=df.index, open=df['Open'], high=df['High'],
    low=df['Low'], close=df['Close'],
    name='Price', increasing_line_color='#26a69a',
    decreasing_line_color='#ef5350'
), row=1, col=1)

# Volume
colors = ['#26a69a' if c >= o else '#ef5350' for c, o in zip(df['Close'], df['Open'])]
fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='Volume',
                      marker_color=colors, opacity=0.5), row=2, col=1)

# Swing points
sh_points = [s for s in swings if s.type == "HIGH"]
sl_points = [s for s in swings if s.type == "LOW"]

fig.add_trace(go.Scatter(
    x=[s.time for s in sh_points], y=[s.price for s in sh_points],
    mode='markers', name='Swing High',
    marker=dict(symbol='triangle-down', size=8, color='#ff9800'),
    hovertemplate='SH: %{y:.2f}<br>%{x}'
), row=1, col=1)

fig.add_trace(go.Scatter(
    x=[s.time for s in sl_points], y=[s.price for s in sl_points],
    mode='markers', name='Swing Low',
    marker=dict(symbol='triangle-up', size=8, color='#2196f3'),
    hovertemplate='SL: %{y:.2f}<br>%{x}'
), row=1, col=1)

# Trade signals
buy_sigs = [s for s in signals if s.direction == "BUY"]
sell_sigs = [s for s in signals if s.direction == "SELL"]

for sig in buy_sigs:
    marker = "✅" if sig.result in ("TP", "CLOSE_REVERSE") else "⚠️" if sig.result == "OPEN" else "❌"
    # Entry marker
    fig.add_trace(go.Scatter(
        x=[sig.time], y=[sig.entry],
        mode='markers+text', name=f'BUY {sig.time.strftime("%H:%M")}',
        marker=dict(symbol='triangle-up', size=14, color='#00e676',
                    line=dict(width=2, color='white')),
        text=[f'{marker} BUY'], textposition='bottom center',
        textfont=dict(size=10, color='#00e676'),
        hovertemplate=(f'<b>BUY {marker}</b><br>'
                      f'Entry: {sig.entry:.2f}<br>'
                      f'SL: {sig.sl:.2f}<br>'
                      f'TP: {sig.tp:.2f}<br>'
                      f'Break: {sig.break_point:.2f} ({sig.break_time.strftime("%H:%M")})<br>'
                      f'Confirm: {sig.confirm_time.strftime("%H:%M")}<br>'
                      f'Retest: {sig.time.strftime("%H:%M")}<br>'
                      f'Result: {sig.result} ({sig.pnl_r:+.1f}R)<extra></extra>')
    ), row=1, col=1)
    # Entry/SL/TP lines
    fig.add_shape(type="line", x0=sig.break_time, x1=sig.time,
                  y0=sig.entry, y1=sig.entry,
                  line=dict(color="#00e676", width=1, dash="dot"), row=1, col=1)
    fig.add_shape(type="line", x0=sig.break_time, x1=sig.time,
                  y0=sig.sl, y1=sig.sl,
                  line=dict(color="#ff1744", width=1, dash="dot"), row=1, col=1)
    # Confirm marker (wave confirmed)
    wc_time = sig.wave_confirm_time or sig.confirm_time
    fig.add_trace(go.Scatter(
        x=[wc_time], y=[sig.entry],
        mode='markers', name='',
        marker=dict(symbol='diamond', size=8, color='#ffeb3b',
                    line=dict(width=1, color='white')),
        hovertemplate=f'Wave Confirmed<br>{wc_time.strftime("%H:%M")}<extra></extra>',
        showlegend=False
    ), row=1, col=1)

for sig in sell_sigs:
    marker = "✅" if sig.result in ("TP", "CLOSE_REVERSE") else "⚠️" if sig.result == "OPEN" else "❌"
    fig.add_trace(go.Scatter(
        x=[sig.time], y=[sig.entry],
        mode='markers+text', name=f'SELL {sig.time.strftime("%H:%M")}',
        marker=dict(symbol='triangle-down', size=14, color='#ff1744',
                    line=dict(width=2, color='white')),
        text=[f'{marker} SELL'], textposition='top center',
        textfont=dict(size=10, color='#ff1744'),
        hovertemplate=(f'<b>SELL {marker}</b><br>'
                      f'Entry: {sig.entry:.2f}<br>'
                      f'SL: {sig.sl:.2f}<br>'
                      f'TP: {sig.tp:.2f}<br>'
                      f'Break: {sig.break_point:.2f} ({sig.break_time.strftime("%H:%M")})<br>'
                      f'Confirm: {sig.confirm_time.strftime("%H:%M")}<br>'
                      f'Retest: {sig.time.strftime("%H:%M")}<br>'
                      f'Result: {sig.result} ({sig.pnl_r:+.1f}R)<extra></extra>')
    ), row=1, col=1)
    fig.add_shape(type="line", x0=sig.break_time, x1=sig.time,
                  y0=sig.entry, y1=sig.entry,
                  line=dict(color="#ff1744", width=1, dash="dot"), row=1, col=1)
    fig.add_shape(type="line", x0=sig.break_time, x1=sig.time,
                  y0=sig.sl, y1=sig.sl,
                  line=dict(color="#ff1744", width=1, dash="dot"), row=1, col=1)
    # Confirm marker (wave confirmed)
    wc_time = sig.wave_confirm_time or sig.confirm_time
    fig.add_trace(go.Scatter(
        x=[wc_time], y=[sig.entry],
        mode='markers', name='',
        marker=dict(symbol='diamond', size=8, color='#ffeb3b',
                    line=dict(width=1, color='white')),
        hovertemplate=f'Wave Confirmed<br>{wc_time.strftime("%H:%M")}<extra></extra>',
        showlegend=False
    ), row=1, col=1)

# Layout
fig.update_layout(
    title=dict(text=f'📈 PA Break v0.7.0 — {SYMBOL} {TIMEFRAME} | '
                    f'{len(signals)} signals | '
                    f'WR {sum(1 for s in signals if s.pnl_r > 0)/max(sum(1 for s in signals if s.result != "OPEN"),1)*100:.0f}% | '
                    f'PnL {sum(s.pnl_r for s in signals):+.2f}R',
               font=dict(size=14)),
    template='plotly_dark',
    xaxis_rangeslider_visible=False,
    height=800,
    showlegend=True,
    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                xanchor="right", x=1),
    hovermode='x unified'
)

fig.update_xaxes(type='category', nticks=30, row=1, col=1)
fig.update_xaxes(type='category', nticks=30, row=2, col=1)

# Export
html_path = '/Users/tuan/GitProject/tradingview/MST Medio/chart_pa_break.html'
fig.write_html(html_path)
print(f"\n✅ Chart exported → {html_path}")

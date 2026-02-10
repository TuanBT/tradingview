import pandas as pd
import sys
sys.path.insert(0, '.')
from strategy_pa_break import find_swings

df = pd.read_csv('data/XAUUSD_M5.csv')
pivotLen = 5
swings = find_swings(df, pivotLen)
dt = df['datetime'].values
O = df['Open'].values
H = df['High'].values
L = df['Low'].values
C = df['Close'].values
n = len(df)

# Simulate Pine Script sh0/sh1 rotation and rawBreakUp detection
sh_points = [(s.price, s.bar_index) for s in swings if s.type == 'HIGH']
sl_points = [(s.price, s.bar_index) for s in swings if s.type == 'LOW']

sh1 = None; sh0 = None; sh1_idx = None; sh0_idx = None
sl1 = None; sl0 = None; sl1_idx = None; sl0_idx = None
slBeforeSH = None; slBeforeSH_idx = None
shBeforeSL = None; shBeforeSL_idx = None

# Index swings by detection bar (bar_index + pivotLen)
swing_at_bar = {}
for s in swings:
    det_bar = s.bar_index + pivotLen
    if det_bar not in swing_at_bar:
        swing_at_bar[det_bar] = []
    swing_at_bar[det_bar].append(s)

pendingState = 0
pendBreakPoint = None
pendW1Peak = None
pendW1Trough = None
pendSL = None
impulseMult = 1.5

for bar in range(n):
    # Process swing detections at this bar
    if bar in swing_at_bar:
        for s in swing_at_bar[bar]:
            if s.type == 'LOW':
                sl0 = sl1; sl0_idx = sl1_idx
                sl1 = s.price; sl1_idx = s.bar_index
            # Important: in Pine Script, swingLow and swingHigh are checked separately
            # and swingLow updates before shBeforeSL check
        for s in swing_at_bar[bar]:
            if s.type == 'HIGH':
                slBeforeSH = sl1; slBeforeSH_idx = sl1_idx
                sh0 = sh1; sh0_idx = sh1_idx
                sh1 = s.price; sh1_idx = s.bar_index
        for s in swing_at_bar[bar]:
            if s.type == 'LOW':
                shBeforeSL = sh1; shBeforeSL_idx = sh1_idx
    
    # Check for HH
    isNewHH = False
    if bar in swing_at_bar:
        for s in swing_at_bar[bar]:
            if s.type == 'HIGH' and sh0 is not None and sh1 > sh0:
                # Impulse filter
                avg_body = sum(abs(C[max(0,bar-20+j)] - O[max(0,bar-20+j)]) for j in range(20)) / 20
                from_bar = bar - sh0_idx
                to_bar = pivotLen
                found = False
                for i in range(from_bar, to_bar - 1, -1):
                    if i < 0: continue
                    if C[bar-i] > sh0:
                        found = abs(C[bar-i] - O[bar-i]) >= impulseMult * avg_body
                        break
                if found and slBeforeSH is not None:
                    isNewHH = True
                elif '2026-02-04' in barDt:
                    reason = "no impulse candle" if not found else "no SL before SH"
                    print(f"  HH rejected @ {barDt}: sh0={sh0:.3f} sh1={sh1:.3f} ({reason})")
    
    barDt = str(dt[bar])[:22]
    
    if isNewHH and pendingState != 2:
        # rawBreakUp — trace what happens
        if '2026-02-04' in barDt:
            # Find W1 peak
            _w1Peak = None
            _w1Bar = None
            _w1TroughInit = None
            _foundBreak = False
            scan_from = bar - sh0_idx
            for i in range(scan_from, -1, -1):
                cl = C[bar-i]; op = O[bar-i]; hi = H[bar-i]; lo = L[bar-i]
                if not _foundBreak:
                    if cl > sh0:
                        _foundBreak = True
                        _w1Peak = hi
                        _w1Bar = bar - i
                        _w1TroughInit = lo
                else:
                    if hi > _w1Peak:
                        _w1Peak = hi
                        _w1Bar = bar - i
                    if _w1TroughInit is None or lo < _w1TroughInit:
                        _w1TroughInit = lo
                    if cl < op:
                        break
            
            if _w1Peak is not None:
                print(f"\nrawBreakUp @ {barDt}")
                print(f"  sh0={sh0:.3f} ({str(dt[sh0_idx])[:22]}), sh1={sh1:.3f}")
                print(f"  SL={slBeforeSH:.3f}, W1Peak={_w1Peak:.3f}")
                print(f"  W1Trough_init={_w1TroughInit:.3f}")
                
                # Quick Phase 1+2 trace
                state = 1
                w1t = _w1TroughInit
                w1_lookback = bar - _w1Bar
                retro_from = max(w1_lookback - 1, 0)
                
                for i in range(retro_from, -1, -1):
                    rH = H[bar-i]; rL = L[bar-i]; rC = C[bar-i]
                    rDt = str(dt[bar-i])[:22]
                    if state == 1:
                        if w1t is None or rL < w1t: w1t = rL
                        if slBeforeSH is not None and rL <= slBeforeSH:
                            print(f"  Phase 1 CANCEL (SL hit) @ {rDt}")
                            state = 0; break
                        if rL <= sh0:
                            print(f"  Phase 1 CANCEL (lo<=Entry) @ {rDt}")
                            state = 0; break
                        if rC > _w1Peak:
                            print(f"  Phase 1 CONFIRM @ {rDt}")
                            state = 2; continue
                    if state == 2:
                        if slBeforeSH is not None and rL <= slBeforeSH:
                            print(f"  Phase 2 CANCEL (SL hit) @ {rDt}")
                            state = 0; break
                        if rL <= sh0:
                            print(f"  Phase 2 SIGNAL @ {rDt}")
                            state = 0; break
                        if w1t is not None and rL <= w1t:
                            print(f"  Phase 2 CANCEL (W1T hit) @ {rDt}")
                            state = 0; break
                    if state == 0: break
                
                if state > 0:
                    print(f"  → Retro ends in state={state}, continues live tracking")
                    pendingState = state
                    pendBreakPoint = sh0
                    pendW1Peak = _w1Peak
                    pendW1Trough = w1t
                    pendSL = slBeforeSH
    
    # Live Phase tracking (simple)
    if pendingState == 2 and pendBreakPoint is not None:
        if pendSL is not None and L[bar] <= pendSL:
            if '2026-02-04' in barDt and int(barDt[11:13]) >= 6:
                print(f"  Phase 2 CANCEL (SL) @ {barDt}")
            pendingState = 0
        elif L[bar] <= pendBreakPoint:
            if '2026-02-04' in barDt and int(barDt[11:13]) >= 6:
                print(f"  SIGNAL BUY @ {barDt}, Entry={pendBreakPoint:.3f}")
            pendingState = 0
        elif pendW1Trough is not None and L[bar] <= pendW1Trough:
            if '2026-02-04' in barDt and int(barDt[11:13]) >= 6:
                print(f"  Phase 2 CANCEL (W1T) @ {barDt}")
            pendingState = 0
    elif pendingState == 1:
        if pendW1Trough is None or L[bar] < pendW1Trough:
            pendW1Trough = L[bar]
        if pendSL is not None and L[bar] <= pendSL:
            if '2026-02-04' in barDt and int(barDt[11:13]) >= 6:
                print(f"  Phase 1 CANCEL (SL) @ {barDt}")
            pendingState = 0
        elif pendBreakPoint is not None and L[bar] <= pendBreakPoint:
            if '2026-02-04' in barDt and int(barDt[11:13]) >= 6:
                print(f"  Phase 1 CANCEL (lo<=Entry) @ {barDt}")
            pendingState = 0
        elif pendW1Peak is not None and C[bar] > pendW1Peak:
            if '2026-02-04' in barDt and int(barDt[11:13]) >= 6:
                print(f"  Phase 1 CONFIRM @ {barDt}")
            pendingState = 2

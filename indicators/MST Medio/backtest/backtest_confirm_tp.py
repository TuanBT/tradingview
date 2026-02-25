"""
Backtest MST Medio with TP = Confirm bar, minimum 1:2 R:R
"""
import pandas as pd
import sys
sys.path.insert(0, '.')
from strategy_pa_break import find_swings

df = pd.read_csv('data/XAUUSD_M5.csv')
pivotLen = 5
impulseMult = 1.5
swings = find_swings(df, pivotLen)

O = df['Open'].values
H = df['High'].values
L = df['Low'].values
C = df['Close'].values
n = len(df)
dt = df['datetime'].values

# Build swing detection by bar (detection = bar_index + pivotLen)
swing_at_bar = {}
for s in swings:
    det_bar = s.bar_index + pivotLen
    if det_bar not in swing_at_bar:
        swing_at_bar[det_bar] = []
    swing_at_bar[det_bar].append(s)

# State variables (mimic Pine Script)
sh1 = sh0 = sh1_idx = sh0_idx = None
sl1 = sl0 = sl1_idx = sl0_idx = None
slBeforeSH = slBeforeSH_idx = None
shBeforeSL = shBeforeSL_idx = None

pendingState = 0
pendBreakPoint = None
pendW1Peak = None
pendW1Trough = None
pendSL = None
pendSL_idx = None
pendBreak_idx = None
waveConfBar = None
waveConfHigh = None
waveConfLow = None

signals = []  # List of (datetime, direction, entry, sl, tp, conf_bar_dt)

for bar in range(n):
    barDt = str(dt[bar])[:22]
    
    # Process swing detections
    if bar in swing_at_bar:
        for s in swing_at_bar[bar]:
            if s.type == 'LOW':
                sl0, sl0_idx = sl1, sl1_idx
                sl1, sl1_idx = s.price, s.bar_index
        for s in swing_at_bar[bar]:
            if s.type == 'HIGH':
                slBeforeSH, slBeforeSH_idx = sl1, sl1_idx
                sh0, sh0_idx = sh1, sh1_idx
                sh1, sh1_idx = s.price, s.bar_index
        for s in swing_at_bar[bar]:
            if s.type == 'LOW':
                shBeforeSL, shBeforeSL_idx = sh1, sh1_idx

    # HH detection with impulse filter
    isNewHH = False
    if bar in swing_at_bar:
        for s in swing_at_bar[bar]:
            if s.type == 'HIGH' and sh0 is not None and sh1 > sh0:
                avg_body = sum(abs(C[max(0, bar-20+j)] - O[max(0, bar-20+j)]) for j in range(20)) / 20
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

    isNewLL = False
    if bar in swing_at_bar:
        for s in swing_at_bar[bar]:
            if s.type == 'LOW' and sl0 is not None and sl1 < sl0:
                avg_body = sum(abs(C[max(0, bar-20+j)] - O[max(0, bar-20+j)]) for j in range(20)) / 20
                from_bar = bar - sl0_idx
                to_bar = pivotLen
                found = False
                for i in range(from_bar, to_bar - 1, -1):
                    if i < 0: continue
                    if C[bar-i] < sl0:
                        found = abs(C[bar-i] - O[bar-i]) >= impulseMult * avg_body
                        break
                if found and shBeforeSL is not None:
                    isNewLL = True

    confirmedBuy = False
    confirmedSell = False
    confEntry = confSL = confConfHigh = confConfLow = None

    # Phase 2: Retest
    if pendingState == 2 and pendBreakPoint is not None:
        if pendSL is not None and L[bar] <= pendSL:
            pendingState = 0
        elif L[bar] <= pendBreakPoint:
            confirmedBuy = True
            confEntry = pendBreakPoint
            confSL = pendSL
            confConfHigh = waveConfHigh
            confConfLow = waveConfLow
            pendingState = 0
        elif pendW1Trough is not None and L[bar] <= pendW1Trough:
            pendingState = 0

    if pendingState == -2 and pendBreakPoint is not None:
        if pendSL is not None and H[bar] >= pendSL:
            pendingState = 0
        elif H[bar] >= pendBreakPoint:
            confirmedSell = True
            confEntry = pendBreakPoint
            confSL = pendSL
            confConfHigh = waveConfHigh
            confConfLow = waveConfLow
            pendingState = 0
        elif pendW1Trough is not None and H[bar] >= pendW1Trough:
            pendingState = 0

    # Phase 1: Confirm
    if pendingState == 1:
        if pendW1Trough is None or L[bar] < pendW1Trough:
            pendW1Trough = L[bar]
        if pendSL is not None and L[bar] <= pendSL:
            pendingState = 0
        elif pendBreakPoint is not None and L[bar] <= pendBreakPoint:
            pendingState = 0
        elif pendW1Peak is not None and C[bar] > pendW1Peak:
            pendingState = 2
            waveConfBar = bar
            waveConfHigh = H[bar]
            waveConfLow = L[bar]

    if pendingState == -1:
        if pendW1Trough is None or H[bar] > pendW1Trough:
            pendW1Trough = H[bar]
        if pendSL is not None and H[bar] >= pendSL:
            pendingState = 0
        elif pendBreakPoint is not None and H[bar] >= pendBreakPoint:
            pendingState = 0
        elif pendW1Peak is not None and C[bar] < pendW1Peak:
            pendingState = -2
            waveConfBar = bar
            waveConfHigh = H[bar]
            waveConfLow = L[bar]

    # New break: BUY
    if isNewHH and pendingState != 2:
        _w1Peak = _w1Bar = _w1TroughInit = None
        _foundBreak = False
        scan_from = bar - sh0_idx
        for i in range(scan_from, -1, -1):
            cl, op, hi, lo = C[bar-i], O[bar-i], H[bar-i], L[bar-i]
            if not _foundBreak:
                if cl > sh0:
                    _foundBreak = True
                    _w1Peak = hi; _w1Bar = bar - i; _w1TroughInit = lo
            else:
                if hi > _w1Peak: _w1Peak = hi; _w1Bar = bar - i
                if _w1TroughInit is None or lo < _w1TroughInit: _w1TroughInit = lo
                if cl < op: break

        if _w1Peak is not None:
            pendingState = 1
            pendBreakPoint = sh0
            pendW1Peak = _w1Peak
            pendW1Trough = _w1TroughInit
            pendSL = slBeforeSH
            pendSL_idx = slBeforeSH_idx
            pendBreak_idx = sh0_idx

            w1_lookback = bar - _w1Bar
            retro_from = max(w1_lookback - 1, 0)
            for i in range(retro_from, -1, -1):
                rH, rL, rC = H[bar-i], L[bar-i], C[bar-i]
                if pendingState == 1:
                    if pendW1Trough is None or rL < pendW1Trough: pendW1Trough = rL
                    if pendSL is not None and rL <= pendSL: pendingState = 0; break
                    if rL <= pendBreakPoint: pendingState = 0; break
                    if rC > pendW1Peak:
                        pendingState = 2
                        waveConfBar = bar - i
                        waveConfHigh = rH
                        waveConfLow = rL
                        continue
                if pendingState == 2:
                    if pendSL is not None and rL <= pendSL: pendingState = 0; break
                    if rL <= pendBreakPoint:
                        confirmedBuy = True
                        confEntry = pendBreakPoint
                        confSL = pendSL
                        confConfHigh = waveConfHigh
                        confConfLow = waveConfLow
                        pendingState = 0; break
                    if pendW1Trough is not None and rL <= pendW1Trough: pendingState = 0; break
                if pendingState == 0: break

    # New break: SELL
    if isNewLL and pendingState != -2:
        _w1Trough = _w1BarSell = _w1TroughInitSell = None
        _foundBrkDn = False
        scan_from = bar - sl0_idx
        for i in range(scan_from, -1, -1):
            cl, op, lo, hi = C[bar-i], O[bar-i], L[bar-i], H[bar-i]
            if not _foundBrkDn:
                if cl < sl0:
                    _foundBrkDn = True
                    _w1Trough = lo; _w1BarSell = bar - i; _w1TroughInitSell = hi
            else:
                if lo < _w1Trough: _w1Trough = lo; _w1BarSell = bar - i
                if _w1TroughInitSell is None or hi > _w1TroughInitSell: _w1TroughInitSell = hi
                if cl > op: break

        if _w1Trough is not None:
            pendingState = -1
            pendBreakPoint = sl0
            pendW1Peak = _w1Trough
            pendW1Trough = _w1TroughInitSell
            pendSL = shBeforeSL
            pendSL_idx = shBeforeSL_idx
            pendBreak_idx = sl0_idx

            w1_lookback = bar - _w1BarSell
            retro_from = max(w1_lookback - 1, 0)
            for i in range(retro_from, -1, -1):
                rH, rL, rC = H[bar-i], L[bar-i], C[bar-i]
                if pendingState == -1:
                    if pendW1Trough is None or rH > pendW1Trough: pendW1Trough = rH
                    if pendSL is not None and rH >= pendSL: pendingState = 0; break
                    if rH >= pendBreakPoint: pendingState = 0; break
                    if rC < pendW1Peak:
                        pendingState = -2
                        waveConfBar = bar - i
                        waveConfHigh = rH
                        waveConfLow = rL
                        continue
                if pendingState == -2:
                    if pendSL is not None and rH >= pendSL: pendingState = 0; break
                    if rH >= pendBreakPoint:
                        confirmedSell = True
                        confEntry = pendBreakPoint
                        confSL = pendSL
                        confConfHigh = waveConfHigh
                        confConfLow = waveConfLow
                        pendingState = 0; break
                    if pendW1Trough is not None and rH >= pendW1Trough: pendingState = 0; break
                if pendingState == 0: break

    # Record signal
    if confirmedBuy:
        signals.append({
            'datetime': barDt,
            'dir': 'BUY',
            'entry': confEntry,
            'sl': confSL,
            'conf_high': confConfHigh,
            'conf_low': confConfLow,
            'signal_bar': bar
        })
    if confirmedSell:
        signals.append({
            'datetime': barDt,
            'dir': 'SELL',
            'entry': confEntry,
            'sl': confSL,
            'conf_high': confConfHigh,
            'conf_low': confConfLow,
            'signal_bar': bar
        })

# Now evaluate each signal with TP = confirm bar, min 1:2 R:R
print(f"{'Datetime':<26} {'Dir':>4} {'Entry':>10} {'SL':>10} {'TP':>10} {'RR':>6} {'(Nat)':>7} {'Result':>8} {'R':>6}")
print("-" * 108)

total_r = 0.0
wins = 0
losses = 0

for sig in signals:
    entry = sig['entry']
    sl = sig['sl']
    direction = sig['dir']
    signal_bar = sig['signal_bar']
    
    if direction == 'BUY':
        risk = entry - sl
        if risk <= 0: continue
        
        # TP = confirm bar high, minimum 1:2 R:R
        natural_tp = sig['conf_high']
        min_tp = entry + 2 * risk
        tp = max(natural_tp, min_tp)
        rr = (tp - entry) / risk

        # Also compute natural TP RR
        natural_rr = (natural_tp - entry) / risk
        
        # Check which hits first
        result = None
        for j in range(signal_bar + 1, n):
            if L[j] <= sl:
                result = 'SL'
                break
            if H[j] >= tp:
                result = 'TP'
                break
        
        if result is None:
            result = 'OPEN'
            r_value = 0
        elif result == 'TP':
            r_value = rr
            wins += 1
        else:
            r_value = -1.0
            losses += 1
        
        total_r += r_value
        print(f"{sig['datetime']:<26} {direction:>4} {entry:>10.3f} {sl:>10.3f} {tp:>10.3f} {rr:>6.2f} ({natural_rr:>5.2f}) {result:>8} {r_value:>+6.2f}")
    
    else:  # SELL
        risk = sl - entry
        if risk <= 0: continue
        
        # TP = confirm bar low, minimum 1:2 R:R
        natural_tp = sig['conf_low']
        min_tp = entry - 2 * risk
        tp = min(natural_tp, min_tp)
        rr = (entry - tp) / risk

        # Also compute natural TP RR
        natural_rr = (entry - natural_tp) / risk
        
        # Check which hits first
        result = None
        for j in range(signal_bar + 1, n):
            if H[j] >= sl:
                result = 'SL'
                break
            if L[j] <= tp:
                result = 'TP'
                break
        
        if result is None:
            result = 'OPEN'
            r_value = 0
        elif result == 'TP':
            r_value = rr
            wins += 1
        else:
            r_value = -1.0
            losses += 1
        
        total_r += r_value
        print(f"{sig['datetime']:<26} {direction:>4} {entry:>10.3f} {sl:>10.3f} {tp:>10.3f} {rr:>6.2f} ({natural_rr:>5.2f}) {result:>8} {r_value:>+6.2f}")

total = wins + losses
wr = (wins / total * 100) if total > 0 else 0
print("-" * 108)
print(f"Total signals: {len(signals)}, Closed: {total}, Wins: {wins}, Losses: {losses}")
print(f"Win Rate: {wr:.1f}%, Total R: {total_r:+.2f}")

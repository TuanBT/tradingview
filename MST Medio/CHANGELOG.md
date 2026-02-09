# MST Medio — Changelog

## v0.1 (2026-02-09)
**Initial version** — Based on PA Break v0.7.0

### Features:
- **Swing Detection** — Pivot-based SH/SL (default `pivotLen=5`)
- **True HH/LL** — Must exceed ALL recent SH/SL, not just the previous one
- **Impulse Body Filter** — Break candle body ≥ 1.5x average (`impulseMult=1.5`)
- **Break Strength Filter** — Break distance ≥ 25% swing range (`breakMult=0.25`)
- **Wave Confirmation** — 2 impulse waves from SH candle (retroactive scan)
- **Retest Entry** — Price returns to break point → entry signal
- **Pre-confirm Retest Invalidation** (SELL only) — Cancel if price retests before wave confirm

### Parameters:
| Param | Default | Description |
|-------|---------|-------------|
| pivotLen | 5 | Lookback for SH/SL |
| breakMult | 0.25 | Break strength threshold |
| impulseMult | 1.5 | Impulse body filter |

### Known Issues:
- `shRecentMax` không reset sau crash lớn → có thể bỏ sót tín hiệu (ví dụ: Jan 30 BUY)

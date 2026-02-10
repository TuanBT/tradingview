# MST Medio — Changelog

## v0.2 (2026-02-10)
**Entry = SH/SL (đỉnh/đáy cũ)** — Logic confirm đúng phương pháp

### Changes:
- **Entry = sh0/sl0** — Đỉnh/đáy cũ bị phá (trước đây dùng sh1/sl1 = đỉnh/đáy mới)
- **W1 peak = sh1** — HH chính là đỉnh W1, không cần đếm wave riêng sau break
- **Confirm = close > W1 peak** — Chỉ cần giá đóng cửa vượt đỉnh W1 (sh1)
- **Cancel nếu chân sóng W1 <= SH** — Low chạm Entry level → phá cấu trúc → cancel
- **Bỏ wave counting phức tạp** — Không đếm W1/W2 bằng candle color nữa
- **Entry/SL labels** — Thêm chữ "Entry" và "SL" trên các đường nét đứt
- **Retroactive scan** — Đơn giản hóa: chỉ check close > W1 peak trong pivot window
- **Line termination** — Đường Entry/SL kết thúc khi close phá qua chân sóng W1 (hoặc SL hit)

### Logic mới:
1. Phát hiện HH (sh1 > sh0) → sh0 = SH = Entry, sh1 = W1 peak
2. Phase 1: Chờ close > sh1 (W1 peak) → Confirm
   - Cancel nếu low <= sh0 (chân sóng W1 về lại SH)
   - Cancel nếu low <= SL
3. Phase 2: Chờ retest tại sh0 → Entry signal

---

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

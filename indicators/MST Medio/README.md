# MST Medio — PA Break Backtest

## Mục đích

Phân tích và backtest chiến lược **MST Medio** (dựa trên PA Break) trên dữ liệu **OANDA:XAUUSD** từ TradingView.  
Dùng cùng AI (GitHub Copilot) để kiểm tra tín hiệu — không cần mở chart web.

---

## Cấu trúc thư mục

```
MST Medio/
  README.md               ← File này
  MST Medio.pine          ← Pine Script indicator cho TradingView
  CHANGELOG.md            ← Lịch sử thay đổi
  data/
    XAUUSD_M5.csv         ← Data backtest cố định (UTC+7)
  strategy_pa_break.py    ← Logic strategy Python (cho phân tích với AI)
```

### Tools (ở ngoài thư mục này)

```
tradingview/
  tools/
    fetch_data.py         ← Module lấy data từ TradingView
    save_data.py          ← Script cập nhật data CSV
    requirements.txt      ← Dependencies: tvdatafeed, pandas, numpy
  .venv/                  ← Python virtual environment
```

---

## Dữ liệu

### Data hiện tại
- **File:** `data/XAUUSD_M5.csv`
- **Symbol:** OANDA:XAUUSD (Gold Spot — giống TradingView)
- **Timeframe:** M5 (5 phút)
- **Timezone:** UTC+7 (Vietnam)
- **Bars:** ~5000 nến (~26 ngày)
- **Format:** CSV với columns: `datetime, Open, High, Low, Close, Volume`

### Cập nhật data mới

```bash
cd tradingview/tools
python save_data.py                     # XAUUSD M5 5000 bars (mặc định)
python save_data.py EURUSD M15 3000     # Tùy chỉnh
```

> ⚠️ Data dùng tvdatafeed (không cần login). Giới hạn ~5000 bars cho M5.

---

## Thuật ngữ giao tiếp với AI

### Timezone
Mọi thời gian đều dùng **UTC+7**. Khi nói "nến 00:40 ngày 30/1" → AI sẽ tra `2026-01-30 00:40:00+07:00` trong data.

### Từ khóa MST Medio

| Từ khóa | Ý nghĩa | Ghi chú |
|---------|---------|---------|
| **SH** | Swing High — **đỉnh cũ** bị phá = **break level** = **entry** | SH cũng chính là Entry point |
| **SL** | Swing Low — đáy xác nhận | Dùng làm Stop Loss cho BUY |
| **HH** | Higher High — đỉnh mới cao hơn đỉnh cũ | Điều kiện để phát hiện break up |
| **LL** | Lower Low — đáy mới thấp hơn đáy cũ | Điều kiện để phát hiện break down |
| **Break** | Giá phá qua SH (break up) hoặc phá qua SL (break down) | |
| **W1** | Wave 1 — **sóng phá** qua SH, tạo đỉnh mới | Trong code: nến tạo HH (sh1 > sh0) |
| **W2** | Wave 2 — **sóng confirm**, tiếp tục theo hướng break | Trong code: wave1 (sóng đầu tiên sau break) |
| **WC** | Wave Confirm — W2 confirm thành công | W2 peak > W1 peak & > SH |
| **Retest** / **RT** | Giá quay lại mức SH (break point) | Điểm vào lệnh |
| **Entry** | Điểm vào lệnh = mức SH bị phá | Entry = SH = break point |
| **Impulse** | Nến có body lớn (≥ 1.5x trung bình 20 nến) | |

### Mapping giữa thuật ngữ và code

| Bạn nói | Trong code Pine/Python |
|---------|----------------------|
| SH (đỉnh cũ bị phá) | `sh0` (previous swing high) |
| W1 (sóng phá) | Nến tạo `sh1` (new HH = break candle) |
| W2 (sóng confirm) | `wave1Peak` trong code |
| WC (wave confirm) | `waveCount == 2` hoặc `wave2Peak > wave1Peak` |
| Entry = SH | `pendBreakPoint = sh1` (nhưng sh1 trong code = đỉnh mới, entry = mức đỉnh cũ bị phá) |

### Luồng tín hiệu BUY
```
SH (đỉnh cũ) → W1 (phá qua SH, tạo đỉnh mới) → W2 (confirm) → WC → Retest về SH → Entry
```

### Luồng tín hiệu SELL
```
SL (đáy cũ) → W1 (phá qua SL, tạo đáy mới) → W2 (confirm) → WC → [no pre-retest] → Retest về SL → Entry
```

### Ví dụ câu nói
- *"Ngày 30/1, SH ở 00:40, W1 ở 03:55, W2 ở 04:25, SL ở 03:00"*
- *"Kiểm tra xem ngày 3/2 có tín hiệu SELL không?"*
- *"Chạy backtest từ ngày 20/1 đến 30/1"*
- *"Nến 19:25 ngày 2/2 là WC đúng không?"*

---

## Strategy v0.1 — MST Medio

### Tham số
| Param | Default | Mô tả |
|-------|---------|-------|
| pivot_len | 5 | Lookback cho SH/SL detection |
| rr_ratio | 2.0 | Risk:Reward ratio (1:2) |
| impulse_mult | 1.5 | Body filter (≥1.5x avg body) |
| break_mult | 0.25 | Break strength (≥25% swing range) |

### Luồng chi tiết (BUY)
1. **HH detected** — Đỉnh mới > tất cả SH gần đây
2. **Impulse check** — Nến phá qua SH có body lớn
3. **Break strength** — Khoảng cách phá ≥ 25% swing range
4. **Wave confirm** — W1 (sóng phá) + W2 (sóng confirm), W2 peak > W1 peak
5. **Retest** — Giá quay lại mức SH (break point)
6. **Entry** — Vào lệnh tại mức SH, SL dưới SL trước đó, TP = 1:2

### Luồng chi tiết (SELL)
Ngược lại BUY. Thêm rule: **Pre-confirm retest invalidation** — nếu giá retest trước khi WC thì hủy (chỉ áp dụng cho SELL).

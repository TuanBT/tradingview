# Changelog — PA Break

## v0.7.0
- **Wave Confirmation** thay thế Swing Confirmation.
  - Phase 1 (Wave Confirm): Sau HH/LL break, track mini-waves theo thay đổi màu nến.
    - Up-wave = chuỗi nến xanh liên tiếp (BUY), Down-wave = chuỗi nến đỏ liên tiếp (SELL).
    - Wave peak bao gồm cả HIGH của nến đầu tiên đổi chiều (râu có thể cao hơn).
    - Xác nhận: Wave 2 peak > Wave 1 peak (BUY) hoặc Wave 2 trough < Wave 1 trough (SELL).
  - Phase 2 (Retest): Sau wave confirm, chờ giá quay về break point (limit order).
- **Entry = Break Point**: Entry = sh1 (cho BUY) hoặc sl1 (cho SELL), thay vì đỉnh/đáy cũ (sh0/shGroupMax).
- **Bỏ Group Tracking**: Không cần shGroupMax/slGroupMin vì entry = break point.
- **Override Protection**: Break mới không override state 2/-2 (đã wave confirm, đang chờ retest).
- **True HH/LL Detection**: Dùng `shRecentMax`/`slRecentMin` track đỉnh/đáy cao/thấp nhất kể từ break trước.
  - HH chỉ hợp lệ khi sh1 ≥ shRecentMax (vượt TẤT CẢ các SH gần đây, không chỉ sh0).
  - LL chỉ hợp lệ khi sl1 ≤ slRecentMin (thấp hơn TẤT CẢ các SL gần đây, không chỉ sl0).
  - Reset trackers sau mỗi break hợp lệ (bắt đầu chu kỳ mới).
  - Lọc false HH/LL: VD. SH 08:35=4904 bị loại vì SH 06:00=4921 cao hơn.
- **States**: 0=idle, 1=pendingBuyWave, 2=pendingBuyRetest, -1=pendingSellWave, -2=pendingSellRetest.
- **Label Position**: Wave ✓ label hiện ở nến xác nhận (confirm candle), không phải tại break point.
- Labels: "▲ Wave ✓" / "▼ Wave ✓".
- Python `strategy_pa_break.py` sync v0.7.0.

## v0.6.0
- **3-Phase Confirmation**: Break → Swing Confirm → Retest Entry.
  - Phase 1 (Swing Confirm): Sau HH/LL break, chờ swing mới xác nhận hướng (swing HIGH > break point cho BUY, swing LOW < break point cho SELL).
  - Phase 2 (Retest Entry): Sau confirm, chờ giá quay về retest đỉnh/đáy cũ → vào lệnh.
  - SL invalidation áp dụng ở cả 2 phase: nếu giá chạm SL trước khi hoàn tất → cancel.
- **States**: 0=idle, 1=pendingBuyConfirm, 2=pendingBuyRetest, -1=pendingSellConfirm, -2=pendingSellRetest.
- **Kết hợp ưu điểm v0.4.0 (swing confirm) + v0.5.0 (retest entry)**: Lọc bỏ false break mà không có swing xác nhận, đồng thời vào lệnh tại retest thay vì tại break.
- Python `strategy_pa_break.py` sync v0.6.0.

## v0.5.1
- **Impulse Body Filter**: Thêm `impulseMult` (default 1.5).
  - Nến ĐẦU TIÊN CLOSE vượt đỉnh/đáy cũ phải có thân (body) ≥ impulseMult × average body (20 bars).
  - Lọc bỏ các break yếu (nến nhỏ hơi vượt đỉnh).
  - Set 0 = OFF.

## v0.5.0
- **Retest Entry**: Thay confirmation state machine bằng retest logic.
  - Sau HH/LL break → chờ giá quay về retest đỉnh/đáy cũ → vào lệnh.
  - Entry = đỉnh cũ (sh0/shGroupMax) cho BUY, đáy cũ (sl0/slGroupMin) cho SELL.
  - Cancel pending nếu giá chạm SL trước khi retest.
- **Bỏ invalidation cũ**: Không cancel khi giá chạm entry (vì chạm entry = retest = vào lệnh!).
- **Bỏ swing confirmation**: Không cần đợi swing mới confirm. Break (HH/LL) → pending → retest → entry.
- Labels đổi thành "▲ Retest ✓" / "▼ Retest ✓".
- Alert messages updated cho retest entry.

## v0.4.0
- **Group Entry**: Entry level is now the strongest swing in the group before the break (shGroupMax for BUY, slGroupMin for SELL) instead of the single previous swing.
- **Break Detection simplified**: Reverted to simple HH/LL (`sh1 > sh0` / `sl1 < sl0`).
- **Strength filter optional**: `breakMult` default = 0 (OFF). Set > 0 to enable.
- **State machine ordering fix**: Confirmation is checked BEFORE new pending breaks are set, preventing missed signals.
- **Full English translation** for TradingView publishing.

## v0.3.0
- **Confirmation State Machine**: Raw breaks now enter a "pending" state. A break is only confirmed when a subsequent swing forms beyond the break point. Pending breaks are invalidated if price revisits the entry level.
- Labels changed to "▲ Break ✓" / "▼ Break ✓" (confirmed only).

## v0.2.0
- **Break Strength filter**: Break distance must exceed `breakMult × previous swing range`.
- **Entry & SL lines**: Dashed lines drawn from entry/SL levels, extending rightward.
- **Cleaner UI**: Separate color inputs for break labels, entry, SL, swings.

## v0.1.0
- Initial release.
- Pivot-based swing detection (HH/LL).
- Break labels on chart.
- Basic alert conditions.

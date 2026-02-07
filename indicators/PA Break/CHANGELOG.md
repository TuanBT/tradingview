# Changelog — PA Break

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

# Conventions (TradingView Indicators Repo)

## Folder rules
Each indicator lives in: `indicators/<indicator_id>/`

Required files:
- One `.pine` file (main code)
- `README.md` (description)
- `CHANGELOG.md`

## Naming rules
- `<indicator_id>`: lowercase, underscores. Example: `fvg_box`, `keylevels_auto`
- Pine filename: `<indicator_id>_v<MAJOR>.<MINOR>.<PATCH>.pine`
  - Example: `fvg_box_v0.3.2.pine`

## Versioning
Use `vMAJOR.MINOR.PATCH`:
- MAJOR: breaking change (inputs renamed/removed, output behavior changed)
- MINOR: new features, non-breaking
- PATCH: bugfix, formatting, perf, UI tweaks

## Pine header (mandatory)
Top of file should contain:
- Indicator name
- ID
- Version
- Purpose
- Notes (repaint/MTF/limits)

## Code layout inside Pine
A) Inputs  
B) Data (including MTF `request.security` if any)  
C) Core logic (calculation, signals)  
D) Plotting / UI (boxes/labels/lines)  
E) Alerts  

## “No-regret” practices
- Keep core logic separate from drawing.
- Use `lookahead_off` for MTF unless you intentionally want repaint.
- Use `barstate.isconfirmed` when you only want signals on bar close.
- Avoid creating unlimited boxes/labels; cap them.

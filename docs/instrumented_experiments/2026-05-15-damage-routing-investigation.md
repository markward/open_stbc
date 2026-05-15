# Damage routing & falloff investigation

Status: **PENDING**
Author: 2026-05-15 session
Created: 2026-05-15
Closed:  —

## Goal

Determine BC's actual damage-routing pipeline for a phaser hit:

1. The falloff curve — is it linear (`MaxDamage × (1 − dist/MaxDamageDistance)`),
   quadratic, capped, or something else?
2. The shield → subsystem → hull split — does the impacted shield face
   absorb 100% first then bleed through only after depletion, or does
   some fraction always pass through?
3. The subsystem-lock effect — when the player has a subsystem locked,
   does **all** sub-shield damage route to that subsystem, or only the
   portion delivered to the matching shield face, or some fixed
   fraction?

Our PR 2c code applies an assumed-linear falloff and a strict cascade
(shields ⇒ subsystem ⇒ hull). Both choices are guesses inherited from
PR 2b. Confirming or refuting them lets us drop the heuristic for the
real BC formula.

## Background

PR 2c's combat tick is in
[`engine/host_loop.py:_advance_combat`](../../engine/host_loop.py)
and uses
[`engine/appc/combat.py:apply_hit`](../../engine/appc/combat.py) for
the per-tick damage routing. The current behavior:

```
damage = MaxDamage × max(0, 1 − dist/MaxDamageDistance) × dt
↓
shields.ApplyDamage(face, damage) → returns remainder
↓
if remainder > 0 and subsystem != hull:
    ship.DamageSystem(subsystem, min(remainder, subsystem.current))
↓
if still remaining: ship.DamageSystem(hull, remaining)
```

Whether this matches BC's behavior is unknown — Appc.dll holds the
real formula. Subsystem-lock routing has the largest uncertainty: BC's
HUD shows a sub-bar for the locked subsystem ticking down during fire,
but we don't know if hull and shields tick down at separate rates,
proportionally, or sequentially.

Related context:

- [`engine/appc/combat.py`](../../engine/appc/combat.py) — current routing.
- [`engine/appc/subsystems.py:ShieldSubsystem.ApplyDamage`](../../engine/appc/subsystems.py) — shield-face damage application.
- [`docs/instrumented_experiments/2026-05-15-phaser-charge-dynamics.md`](2026-05-15-phaser-charge-dynamics.md) — partner experiment (run separately).

## Specific questions

Each must end with a numeric answer in the **Findings** section.

- **Q-D1** With phasers held continuously and target at **point-blank
  range** (≪ MaxDamageDistance), what is `damage_per_second` actually
  delivered? Compare to `MaxDamage × num_banks_firing` to confirm the
  full-damage anchor of the falloff.
- **Q-D2** At **half MaxDamageDistance** range, does delivered DPS
  scale to ~50% (linear), ~25% (quadratic), or something else?
- **Q-D3** At exactly `MaxDamageDistance` range, does delivered DPS
  hit zero, or is there a residual?
- **Q-D4** While the **impacted shield face** is alive, does **all**
  damage subtract from `shield_face_current`, or does some bleed to
  hull immediately?
- **Q-D5** Once that shield face is **depleted** (current = 0), what's
  the split between subsystem and hull damage per tick? Is it
  100/0 (all subsystem until destroyed), proportional, or something
  else?
- **Q-D6** With a **subsystem locked** by the player (Tab + Subsystem
  picker), where does the damage go while shields are still up? Same
  as no-lock (just hits the face), or does some fraction route
  immediately to the locked subsystem?
- **Q-D7** With shields **gone** + subsystem locked, is the locked
  subsystem damaged at a higher rate than hull (e.g. 100% subsystem
  until destroyed, then hull), or split (e.g. 50/50)?

## Snippet

Save as `tools/damage_logger.py`. Same install path as
[`tools/appc_logger.py`](../../tools/appc_logger.py) — `tools/setup.py`
will append it to `game/scripts/App.py` after we point it there (step 2
of *How to run*).

The snippet samples once per tick (downsampled) the **target ship's**
shield faces, hull, and the player-locked subsystem condition values.
A separate row also captures the range from player to target so the
analyzer can correlate ranges with deltas.

```python
###############################################################################
# damage_logger.py
#
# Appended to game/scripts/App.py by tools/setup.py — captures per-tick
# target-state changes during phaser fire. See
# docs/instrumented_experiments/2026-05-15-damage-routing-investigation.md.
#
# Hooks UtopiaModule.GetGameTime (per-tick heartbeat). On every Nth tick
# we sample:
#   - player phaser bank 0 firing flag (so analyzer can window fire bursts)
#   - target ship's shield face currents (6 faces), hull current, locked
#     subsystem current (if any)
#   - range from player to target
# A ring of up to MAX_SAMPLES rows is written to BCDamageLog.cfg.
#
# Python 1.5 constraints (see CLAUDE.md "Critical constraints"):
#   - no f-strings, no True/False literals, no "import X as Y"
#   - guard every import with try/except ImportError
#   - file I/O ONLY via g_kConfigMapping.SaveConfigFile
#   - os module is not available; only sys is reliably present
###############################################################################
try:
    _samples = []
    _MAX_SAMPLES = 900           # 90 seconds at 10 Hz
    _SAMPLE_EVERY_N_TICKS = 6    # ~10 Hz at 60 Hz fixed step
    _save_every = 0
    _SAVE_EVERY_N_SAMPLES = 30   # cfg flushed ~3x/sec
    _tick_counter = 0
    _orig_GetGameTime = UtopiaModule.GetGameTime

    def _safe_call(obj, attr):
        try:
            return getattr(obj, attr)()
        except:
            return None

    def _safe_call1(obj, attr, arg):
        try:
            return getattr(obj, attr)(arg)
        except:
            return None

    def _bank0_firing(player):
        try:
            ph = player.GetPhaserSystem()
            if ph is None or ph.GetNumWeapons() == 0:
                return -1
            f = ph.GetWeapon(0).IsFiring()
            if f is None: return -1
            return int(f)
        except:
            return -1

    def _shield_face_currents(target):
        try:
            sh = target.GetShields()
        except:
            sh = None
        if sh is None:
            return ["-1.0"] * 6
        out = []
        for face in range(6):
            v = _safe_call1(sh, "GetCurrentShields", face)
            if v is None:
                out.append("-1.0")
            else:
                out.append("%.4f" % v)
        return out

    def _hull_current(target):
        try:
            hull = target.GetHull()
            if hull is None: return -1.0
            v = hull.GetCondition()
            if v is None: return -1.0
            return v
        except:
            return -1.0

    def _locked_subsystem_current(player):
        try:
            sub = player.GetTargetSubsystem()
            if sub is None: return -1.0
            v = sub.GetCondition()
            if v is None: return -1.0
            return v
        except:
            return -1.0

    def _locked_subsystem_name(player):
        try:
            sub = player.GetTargetSubsystem()
            if sub is None: return ""
            return sub.GetName()
        except:
            return ""

    def _range_to_target(player, target):
        try:
            p = player.GetWorldLocation()
            t = target.GetWorldLocation()
            dx = t.x - p.x; dy = t.y - p.y; dz = t.z - p.z
            return (dx*dx + dy*dy + dz*dz) ** 0.5
        except:
            return -1.0

    def _sample(game_t):
        try:
            import time
            wall = time.time()
        except:
            wall = 0.0
        try:
            frame = g_kSystemWrapper.GetUpdateNumber()
        except:
            frame = 0
        try:
            player = Game_GetCurrentPlayer()
        except:
            player = None
        if player is None:
            return ("%.4f" % wall, "%.4f" % game_t, "%d" % frame,
                    "-1", "-1.0", "-1.0",
                    "-1.0","-1.0","-1.0","-1.0","-1.0","-1.0",
                    "-1.0", "")
        try:
            target = player.GetTarget()
        except:
            target = None
        firing0 = _bank0_firing(player)
        sub_cur = _locked_subsystem_current(player)
        sub_name = _locked_subsystem_name(player)
        if target is None:
            return ("%.4f" % wall, "%.4f" % game_t, "%d" % frame,
                    "%d" % firing0, "-1.0", "%.4f" % sub_cur,
                    "-1.0","-1.0","-1.0","-1.0","-1.0","-1.0",
                    "-1.0", sub_name)
        rng = _range_to_target(player, target)
        hull_cur = _hull_current(target)
        faces = _shield_face_currents(target)
        return ("%.4f" % wall, "%.4f" % game_t, "%d" % frame,
                "%d" % firing0, "%.4f" % rng, "%.4f" % sub_cur,
                faces[0], faces[1], faces[2], faces[3], faces[4], faces[5],
                "%.4f" % hull_cur, sub_name)

    _COLUMNS = ("wall game_t frame firing0 range sub_current "
                "shield_F shield_R shield_T shield_B shield_L shield_RT "
                "hull_current sub_name")

    def _flush(cfg):
        cfg.SetIntValue("BCDamageLog", "n_samples", len(_samples))
        if _samples:
            cfg.SetStringValue("BCDamageLog", "first_sample",
                                " ".join(_samples[0]))
            cfg.SetStringValue("BCDamageLog", "last_sample",
                                " ".join(_samples[-1]))
        for i in range(len(_samples)):
            cfg.SetStringValue("BCDamageLog", "s%d" % i, " ".join(_samples[i]))
        cfg.SetStringValue("BCDamageLog", "columns", _COLUMNS)
        try:
            cfg.SaveConfigFile("BCDamageLog.cfg")
        except:
            pass

    def _GetGameTime_wrapped():
        global _tick_counter, _save_every
        result = _orig_GetGameTime()
        _tick_counter = _tick_counter + 1
        if _tick_counter % _SAMPLE_EVERY_N_TICKS != 0:
            return result
        _samples.append(_sample(result))
        if len(_samples) > _MAX_SAMPLES:
            del _samples[0]
        _save_every = _save_every + 1
        if _save_every >= _SAVE_EVERY_N_SAMPLES:
            _save_every = 0
            try:
                _flush(g_kConfigMapping)
            except:
                pass
        return result

    UtopiaModule.GetGameTime = _GetGameTime_wrapped
except Exception, _instr_err:
    try:
        g_kConfigMapping.SetStringValue("BCDamageLog", "instr_error",
                                         "%s: %s" % (_instr_err.__class__.__name__,
                                                      str(_instr_err)))
        g_kConfigMapping.SaveConfigFile("BCDamageLog.cfg")
    except:
        pass
```

Sample row format (space-separated, one per `s<index>` key):

```
wall game_t frame firing0 range sub_current shield_F shield_R shield_T shield_B shield_L shield_RT hull_current sub_name
1731.4321 12.3456 740 1 350.21 600.000 8000.0 4000.0 4000.0 4000.0 4000.0 4000.0 22000.0 "Impulse Engines"
```

`sub_name` is the locked subsystem's name (or empty when no
subsystem-lock). The cfg's first row tells you which subsystem the
player happened to lock so the analyzer can match the column.

## How to run

This experiment runs on a **Windows machine with BC installed at
`game/`**. The macOS dev box can prepare and analyze the cfg but cannot
run stbc.exe.

1. **Drop the snippet** at `tools/damage_logger.py` (copy from the
   "Snippet" section above verbatim).

2. **Swap the instrumentation snippet.** Edit
   [`tools/setup.py:26`](../../tools/setup.py#L26):

   ```diff
   - SHIM_SNIPPET = PROJECT_ROOT / "tools" / "appc_logger.py"
   + SHIM_SNIPPET = PROJECT_ROOT / "tools" / "damage_logger.py"
   ```

3. **Install** into `game/scripts/App.py`:

   ```
   uv run python tools/setup.py            # uses cached .pyc
   uv run python tools/setup.py --recompile  # first run after snippet edit
   uv run python tools/setup.py --capture    # cache the new .pyc
   ```

4. **Launch BC, load Quick Battle** with **Galaxy** as the player and
   one **Galaxy-class** enemy. RED alert, no subsystem-lock yet. Tab to
   acquire the enemy.

5. **Point-blank pass (Q-D1):** Close to ≤ 50 units of the target.
   Hold LBUTTON for 5 seconds. Release. Capture name:

   ```powershell
   Copy-Item game\BCDamageLog.cfg game\BCDamageLog.pointblank.cfg
   ```

6. **Mid-range pass (Q-D2):** Pull back to ~30 units (eyeball half of
   the green target-range bar, which IS `MaxDamageDistance` for Galaxy
   phasers, scaled visually). Hold LBUTTON for 5 seconds. Capture:

   ```powershell
   Copy-Item game\BCDamageLog.cfg game\BCDamageLog.midrange.cfg
   ```

7. **Long-range pass (Q-D3):** Pull back to just beyond the green
   range bar (target is gray in HUD). Hold LBUTTON for 5 seconds.
   Capture:

   ```powershell
   Copy-Item game\BCDamageLog.cfg game\BCDamageLog.longrange.cfg
   ```

8. **Subsystem-lock pass (Q-D6/Q-D7):** Restart Quick Battle for fresh
   shields. Tab + use the subsystem picker to lock the enemy's
   **Impulse Engines**. Hold LBUTTON for 10 seconds at point-blank
   (so we get shielded + unshielded data in one capture as the shield
   face depletes). Capture:

   ```powershell
   Copy-Item game\BCDamageLog.cfg game\BCDamageLog.sublock.cfg
   ```

9. **Quit BC.**

10. **Send the four cfgs back** to the macOS dev box.

11. **Analyze on macOS** with a one-off script. Pseudocode:

    ```python
    # Parse [BCDamageLog]. Build per-cfg time series:
    #   (game_t, firing0, range, shield_F..RT, hull, sub_current)
    #
    # Q-D1 (point-blank DPS):
    #   In the pointblank.cfg, find the fire window (firing0 1→0 transitions).
    #   Compute total damage delivered = (initial_total - final_total) where
    #   total = shield_F + shield_R + ... + hull. Divide by window duration.
    #   Number of banks firing ≈ 8 for Galaxy at RED alert in arc.
    #   Compare DPS to MaxDamage(=250) × 8 banks. Discrepancy = falloff at 0.
    #
    # Q-D2 (mid-range DPS):
    #   Same in midrange.cfg.  Ratio to point-blank DPS reveals falloff shape:
    #     ~0.5  → linear (1 - r/R)
    #     ~0.25 → quadratic
    #
    # Q-D3 (max range):
    #   longrange.cfg.  Should approach zero.
    #
    # Q-D4 (shield face vs hull while face alive):
    #   In any cfg, the first few seconds. shield_F deltas vs hull deltas.
    #   If hull stays flat while shield_F drops → 100% absorption pre-depletion.
    #
    # Q-D5 (split after face depleted):
    #   Find the tick where shield_F goes 0. From that tick onward, compute
    #   per-tick (hull_delta, sub_current_delta).  Ratio reveals split.
    #
    # Q-D6 (subsystem-lock while shielded):
    #   In sublock.cfg, before shield_F = 0, look at sub_current deltas.
    #   If non-zero → fraction bleeds to locked subsystem through shields.
    #
    # Q-D7 (subsystem-lock unshielded):
    #   From shield_F=0 onward in sublock.cfg, compare sub_current vs hull
    #   deltas. Ratio = locked-subsystem priority.
    ```

12. **Update this doc.** Move Status to **DONE**, fill in Findings,
    paste the analyzer output. Commit.

## Expected output

```
[BCDamageLog]
n_samples=900
columns=wall game_t frame firing0 range sub_current shield_F shield_R shield_T shield_B shield_L shield_RT hull_current sub_name
first_sample=...
last_sample=...
s0=1731.0000 0.1500 9 0 -1.0 -1.0 8000.0 4000.0 4000.0 4000.0 4000.0 4000.0 22000.0
...
s50=1735.1000 5.1500 309 1 40.21 -1.0 7400.0 4000.0 4000.0 4000.0 4000.0 4000.0 22000.0
s51=1735.2000 5.3000 318 1 40.18 -1.0 7150.0 4000.0 4000.0 4000.0 4000.0 4000.0 22000.0
...
s120=1742.0000 12.0000 720 0 40.20 -1.0 0.0 4000.0 4000.0 4000.0 4000.0 4000.0 19500.0
...
```

(Numbers illustrative — the actual deltas IS the answer.)

## Cleanup

After the experiment is done — **always** run these, even if BC
crashed mid-experiment:

1. **Uninstall:**

   ```
   uv run python tools/uninstall.py
   ```

2. **Revert the `tools/setup.py` edit** from step 2:

   ```diff
   - SHIM_SNIPPET = PROJECT_ROOT / "tools" / "damage_logger.py"
   + SHIM_SNIPPET = PROJECT_ROOT / "tools" / "appc_logger.py"
   ```

3. **Leave `tools/damage_logger.py` in place** for re-runs.

## Findings

*(Pending the Windows session — fill in once the cfgs are captured.)*

- **Q-D1** — Point-blank DPS vs `MaxDamage × num_banks`: _TBD_
- **Q-D2** — Falloff shape (linear / quadratic / other): _TBD_
- **Q-D3** — Damage at exactly MaxDamageDistance: _TBD_
- **Q-D4** — Shield-face absorption fraction pre-depletion: _TBD_
- **Q-D5** — Subsystem vs hull split post-depletion: _TBD_
- **Q-D6** — Subsystem-lock bleed-through while shielded: _TBD_
- **Q-D7** — Subsystem-lock priority unshielded: _TBD_

Once filled in, replace
[`engine/appc/combat.py:apply_hit`](../../engine/appc/combat.py)'s
heuristic split with the verified ratios, and replace the assumed
linear falloff in
[`engine/host_loop.py:_phaser_damage_for_tick`](../../engine/host_loop.py)
with the measured curve.

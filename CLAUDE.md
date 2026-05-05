# open_stbc — Claude Context

## What this project is

Open reimplementation of the Star Trek: Bridge Commander (BC) engine, targeting modern operating systems. The long-term deliverable is a new C++ engine that runs BC's original Python game scripts without the original Windows-only `Appc.dll`.

The original engine is a compiled C++ binary exposed to Python via a SWIG-generated interface (`App.py`). Everything the game does crosses that boundary. The plan is to reverse-engineer and replace `Appc` with a modern, cross-platform C++ engine that embeds CPython.

## Current stage

**Discovery and analysis.** We are resolving open questions in `docs/gap_analysis.md` and `docs/open_questions.md` before any significant implementation. The repo is set up on a Windows machine to enable instrumentation of the live game installation.

## Implementation phases

**Phase 1 — Headless logic engine** (3–6 months)
- Replace `Appc` with a Python shim
- Physics via PyBullet
- Event system from scratch
- No renderer
- Goal: run the SDK tutorial missions and validate all game logic

**Phase 2 — Full C++ engine** (18 months+)
- OpenMW NIF renderer extended with BC-specific block types (NifSkope has BC support)
- OpenAL audio
- Character animation
- CPython embedding layer

## Key reference material

| Resource | Location | Purpose |
|---|---|---|
| Appc interface spec | `sdk/Build/scripts/App.py` | Complete surface of every engine call — SWIG-generated, fully readable |
| SDK Python source | `sdk/Build/scripts/` | 1228 files; ground truth for all game logic |
| Physics parameters | `sdk/Build/scripts/GlobalPropertyTemplates.py` | Mass, rotational inertia per ship class |
| Ship hardpoints | `sdk/Build/scripts/ships/Hardpoints/` | Per-ship physics, weapons, arc geometry |
| Ship construction | `sdk/Build/scripts/loadspacehelper.py:54–135` | Integration point between Appc and physics |
| Mission lib | `sdk/Build/scripts/MissionLib.py` | Timer lifecycle, two-tier timer architecture |
| Gap analysis | `docs/gap_analysis.md` | 8 gaps, 21 open questions, solution paths |
| Open questions | `docs/open_questions.md` | 4 instrumentation questions — Q4 closed |
| Live game | `game/` | BC installation (gitignored) — needed for instrumentation |

## Open questions status

### Instrumentation questions (require running game)

| Q | Topic | Status |
|---|---|---|
| Q1 | Tick rate — fixed or variable? what Hz? | ❌ Open — resolve first |
| Q2 | Subsystem update ordering within a tick | ❌ Open — resolve before AI integration |
| Q3 | Time scale interaction with physics/AI/timers | ⚠️ Partial |
| Q4 | TimeSliceProcess priority semantics | ✅ Closed — static analysis sufficient |

**Q1 is the highest priority.** It unblocks physics and timer implementation. Instrumentation: log `GetUpdateNumber` with wall-clock timestamps, average deltas over 30 seconds.

### Gap analysis OQs (21 total)

- Closed by static analysis: OQ-1.1, 1.2, 1.3, 4.1, 7.4
- Partially answered: OQ-2.1 (degradation formula), OQ-4.2 (dispatch ordering)
- Still open: 14 OQs across gaps 2, 3, 4, 5, 6, 7, 8

**Phase 1 blockers:** OQ-2.1, OQ-4.2, OQ-7.1 (= Q1), OQ-7.2 (= Q2)

## Instrumentation approach

`tools/appc_logger.py` is a drop-in `Appc` logging shim. Replace the real `Appc` module with this before BC starts — all engine calls are intercepted and logged with arguments, return values, and wall-clock timestamps. No native tooling or debugger required.

## Key architectural facts

- Object hierarchy: `ObjectClass → PhysicsObjectClass → DamageableObject → ShipClass`
- Python owns Appc objects it creates; must explicitly clean up in `__del__` via engine calls
- Save/load: 39 classes use `__getstate__`/`__setstate__`; saves Python-side state only, re-looks up Appc handles on restore
- `PythonMethodProcess` cannot be pickled — must be recreated in `__setstate__`
- Two independent time streams: `g_kTimerManager` (game time) and `g_kRealtimeTimerManager` (wall clock)
- Loop is single-threaded from Python's perspective (`sys.setcheckinterval(200)` in `Autoexec.py`)
- Python priority levels actually used: `NORMAL` (most things) and `LOW` (2 scripts only); `CRITICAL`/`UNSTOPPABLE` are C++ internal

## Setup

```bash
# Drop BC installation into game/, BC SDK v1.1 into sdk/
uv sync
uv run pytest
```

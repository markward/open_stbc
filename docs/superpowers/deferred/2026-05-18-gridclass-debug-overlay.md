# Deferred: GridClass debug overlay

**Status:** deferred 2026-05-18. Decision: ship option A — a no-op `GridClass` shim in [`App.py`](../../../App.py) that satisfies the SDK's creation boilerplate without rendering anything. Option B (real wireframe debug overlay in the C++ renderer) deferred until the empirical test below confirms the grid is renderable in the original engine *and* an independent need for a debug overlay arises.

## Context

The gameloop harness profile (`tools/gameloop_harness.py --profile`, 36000 ticks × 35 missions) reported `GridClass_Create` and its `.SetHidden` / `.SetName` follow-ups as the top three un-implemented App-shim attributes — 30 missions, 122 calls each. Every call originates from the same auto-generated three-line boilerplate in `Systems/*/<region>.py` and the two `Maelstrom/Episode5/E5M[24]` mission files:

```python
pGrid = App.GridClass_Create()
pSet.AddObjectToSet(pGrid, "grid")
pGrid.SetHidden(1)
```

## Why option A is sufficient

Audited the entire SDK ([`sdk/Build/scripts/`](../../../sdk/Build/scripts/)):

- **No `SetHidden(0)` anywhere.** The grid is created hidden in every region and never shown.
- **Nobody calls the configuration API.** `SetLineLength`, `SetStep`, `UpdatePosition`, `Update` are all exported (see [`sdk App.py:9034-9039`](../../../sdk/Build/scripts/App.py#L9034-L9039)) but unused by Python.
- **No retrieval.** No `pSet.GetObject("grid")`, no later mutation. The reference `pGrid` is dropped at the end of `Initialize` and the object becomes effectively unreachable.
- **Identical boilerplate everywhere** (40+ region files plus two Maelstrom missions), prefaced by the same comment `#Load and place the grid.` — signature of editor-emitted code that lost its purpose before shipping.

From the Python game's perspective the grid is inert. A class with default-hidden state and no-op setters fully satisfies the contract.

## Hypothesis about the original engine (unverified)

The full method surface is wired through SWIG to real `Appc.GridClass_*` symbols, so the C++ renderer code for the grid almost certainly still compiles into the shipped Appc.dll. Most plausible reading: the grid was a developer positioning aid — a wireframe XY reference plane used while authoring star-system regions in the level editor — toggleable from the C++ side (hotkey, dev console) but never exposed to the Python game once authoring was done.

This is inference from API surface, not measurement.

## Revisit trigger — the empirical test

Drop these lines into a region you'll fly through (e.g. [`Systems/Biranu/Biranu1.py:21`](../../../sdk/Build/scripts/Systems/Biranu/Biranu1.py#L21), right after the existing grid setup):

```python
pGrid.SetLineLength(2000.0)
pGrid.SetStep(100.0)
pGrid.SetHidden(0)
```

Load that system in the original Bridge Commander. Two possible outcomes:

- **Wireframe XY plane appears.** Hypothesis confirmed: the dev overlay is alive in the shipped binary. Reopen this doc and consider option B (build a real wireframe-grid pass in `native/` keyed off `_hidden=False` and a dev toggle). Useful for debugging positions/sets independently of the SDK boilerplate.
- **Nothing visible.** Option A is unambiguously correct and this doc closes. The C++ render path was likely stripped or gated on a debug build flag.

## Option A implementation (delivered separately)

- Promote the placeholder [`class Grid(ObjectClass): pass`](../../../App.py#L174) to a real `GridClass` with `_hidden=True` default and no-op setters: `SetLineLength`, `GetLineLength`, `SetStep`, `GetStep`, `UpdatePosition`, `Update`.
- Add `def GridClass_Create(): return GridClass()` at module scope so the SDK's `App.GridClass_Create()` resolves before hitting `_NamedStub`.
- Keep `Grid = GridClass` and `CT_GRID = GridClass` so any code reading the type constant still works.
- Re-run `tools/gameloop_harness.py --profile` and confirm the three rows disappear from the report.

## Option B (deferred work — only if the empirical test renders something)

- Wireframe XY-grid pass in `native/src/renderer/`, anchored on `GridClass` instances added to the active set, drawn only when `_hidden=False`.
- Independent dev toggle (function key, on the same control surface as the existing F-key debug toggles) — do not rely on the SDK's `SetHidden(0)`, since no shipping mission sets it.
- Parameters from `_line_length` and `_step`, defaulting to whatever the original used (TBD — extract from the test region above once visible).
- Out of scope for option B: editor integration, save/load of grid state, runtime reconfiguration via Python.

## Files in scope

| File | Relevance |
|---|---|
| [`App.py`](../../../App.py) | Promote `Grid` → `GridClass`, add `GridClass_Create` factory |
| [`tools/gameloop_harness.py`](../../../tools/gameloop_harness.py) | Verify profile rows clear after option A |
| [`sdk/Build/scripts/Systems/Biranu/Biranu1.py`](../../../sdk/Build/scripts/Systems/Biranu/Biranu1.py) | Recommended test region for the empirical experiment |

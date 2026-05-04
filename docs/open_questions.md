# Open Questions for Python Injection Investigation

These questions cannot be answered from static analysis of the source alone.
Each requires a targeted instrumentation session against the running game.
All are answerable via the `Appc` wrapper logging approach before significant
reimplementation work begins.

---

## Q1 — Tick Rate

**Question:** What is the game loop tick rate? Is it fixed or variable?

**Why it matters:** All `TimeSliceProcess` delays are specified in seconds.
Their actual granularity depends on how often the loop ticks. Physics
integration accuracy and AI polling intervals are both affected.

**Instrumentation approach:** Log `GetUpdateNumber` with a wall-clock
timestamp on each change. Average deltas over 30 seconds of gameplay.
Check variance to determine fixed vs variable.

**Expected answer:** Likely 20Hz or 30Hz fixed simulation tick, based on
timer granularity visible in source and era of engine.

---

## Q2 — Subsystem Update Ordering Within a Tick

**Question:** Within a single tick, what order do subsystems update?
Specifically — does physics integrate before or after AI runs? Do events
fire before or after physics? Does Python get called before or after
the renderer?

**Why it matters:** An AI reading a ship position before physics has
integrated for that frame will make different decisions than one reading
after. Ordering affects correctness of combat AI and mission trigger timing.

**Instrumentation approach:** Log `GetUpdateNumber` alongside every
significant `Appc` call category — physics reads, AI callbacks, event
dispatch, render calls. Sort by frame number and wall-clock time to
reconstruct the within-tick call sequence.

**Specific calls to watch:**
- `PhysicsObjectClass` position/velocity reads and writes
- `ArtificialIntelligence` update callbacks
- `TGEventManager` dispatch calls
- `TGTimerManager` tick calls

---

## Q3 — Time Scale Interaction with Physics and AI

**Question:** When `SetTimeScale()` is called (e.g. for slow motion cinematic
mode), does the physics integrator receive a scaled delta-time, or is
something else happening? Does AI decision-making slow proportionally?
Do `g_kTimerManager` timers slow while `g_kRealtimeTimerManager` timers
continue at wall-clock speed?

**Why it matters:** Determines whether slow mode is purely cosmetic
(renderer slows, logic continues at full rate) or whether it genuinely
scales the entire simulation. Affects how `SetTimeScale` must be
implemented in the replacement engine.

**Instrumentation approach:** Call `SetTimeScale(0.5)` during a session.
Log `GetGameTime` and `GetRealTime` readings at each frame alongside
`GetUpdateNumber`. Measure AI callback frequency and timer fire times
relative to both clocks.

**Specific scenario:** Trigger a cinematic sequence that uses slow mode,
log throughout, compare game time progression to real time progression.

---

## Q4 — TimeSliceProcess Priority Semantics

**Question:** What do the four priority levels (`UNSTOPPABLE`, `CRITICAL`,
`NORMAL`, `LOW`) actually mean in practice? Does `UNSTOPPABLE` run every
tick regardless of frame budget? Can `LOW` priority processes be skipped
or deferred when the frame is over budget? Is there observable difference
between `NORMAL` and `LOW` under normal gameplay conditions?

**Why it matters:** `PythonMethodProcess` inherits from `TimeSliceProcess`.
If priority affects whether a process fires on a given tick, condition
polling intervals may not be as reliable as assumed. Combat AI correctness
could be affected if `LOW` priority processes are skipped under load.

**Instrumentation approach:** Create processes at each priority level with
known delays. Log actual fire times relative to expected fire times under
both low and high simulation load (many ships, active combat). Compare
regularity across priority levels.

**Note:** Static analysis suggests almost all Python-visible usage is
`NORMAL` priority. Exotic priorities may only be used internally by the
engine for rendering and physics. This question may have low practical
impact but should be confirmed before assuming reliable polling intervals.

---

## Investigation Priority

| Question | Impact if wrong | Instrumentation effort |
|---|---|---|
| Q1 Tick rate | High — affects all timing | Very low — 5 minutes |
| Q2 Update ordering | Medium-high — affects AI/physics interaction | Medium — one focused session |
| Q3 Time scale | Medium — affects cinematic mode only | Low — trigger one cinematic |
| Q4 Process priorities | Low — likely internal only | Medium — requires load testing |

**Recommended order:** Q1 first (quick win, unblocks everything else),
Q3 second (quick, self-contained), Q2 third (requires more careful
instrumentation setup), Q4 last (lowest priority, may be skipped if
resources are constrained).

---

## Notes

- All four questions are answerable in a single instrumentation session
  if the `Appc` wrapper logging infrastructure is in place.
- Q1 should be answered before any physics or timer implementation work begins.
- Q2 should be answered before AI integration work begins.
- Q3 and Q4 can be deferred until cinematic/priority features are being
  implemented.
- The BC modding community documentation may already answer Q1 — check
  BCFiles and related modding wikis before instrumentation.

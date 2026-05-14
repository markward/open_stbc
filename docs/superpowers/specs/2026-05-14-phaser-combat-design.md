# PR 2c — Phaser Combat

**Status:** Spec, ready for implementation plan.
**Builds on:** PR 2a (weapon firing pipeline + alert-driven power), PR 2b (torpedo combat — `apply_hit`, shield-impact splash, direction gating, per-tube spawn positions).
**Scope:** Player-side phasers only. PulseWeapon and TractorBeam deferred to later PRs. AI does not return fire.

## Goal

Hold left-click with a target locked → every PhaserBank on the player ship whose arc covers the target fires a continuous BC-faithful beam, dealing distance-falloff damage through the existing combat pipeline. Release left-click → all banks stop. Visible beams use BC's additive textured-quad convention.

## Architecture

The PR reuses everything PR 2a + 2b built:

- `apply_hit` already routes damage through shields → subsystem → hull and emits `WeaponHitEvent`.
- `host.shield_hit` already produces a bubble splash on the target.
- `_EnergyWeaponFireMixin` already handles charge model and Fire / StopFiring / UpdateCharge.
- `PoweredSubsystem.IsOn()` is already alert-driven (GREEN → off, RED → on).
- Round-robin emitter dispatch already exists for torpedoes; phasers replace it with simultaneous multi-bank fire.

What this PR adds: an arc-aware firing gate, a per-tick damage application for firing banks, and a beam render pass.

Data flow per tick:

```
LBUTTON down + target locked
  → PhaserSystem.StartFiring(target)
    → for each PhaserBank where alert + arc + charge allow:
        bank._firing = True; bank._target = target; play "X Start" SFX
  → host_loop._advance_combat:
      for each bank where IsFiring():
        damage = MaxDamage × max(0, 1 − dist/MaxDamageDistance) × dt
        apply_hit(target_ship, damage, hit_point=target_pos, subsystem=target_sub)
        # apply_hit already triggers host.shield_hit for the splash
  → host_loop._build_phaser_beam_data:
      for each firing bank: (emitter_world_pos, target_world_pos, color, width)
  → host.set_phaser_beams(...) → PhaserPass.render
LBUTTON up
  → PhaserSystem.StopFiring()
    → for each firing bank: bank._firing = False; play "X Stop" SFX
```

## Components

### 1. Arc gate

**File:** `engine/appc/subsystems.py`

Replace `_emitter_faces` (current 90° cone) with `_emitter_in_arc`. For emitters that have explicit `SetArcWidthAngles(yaw_min, yaw_max)` / `SetArcHeightAngles(pitch_min, pitch_max)`:

1. Build a body-frame basis from the emitter's `SetDirection` (forward) + `SetRight` axes. Up = direction × right.
2. Compute body-space vector from emitter position to target.
3. Project onto direction/right/up to get yaw = `atan2(right·v, fwd·v)` and pitch = `asin(up·v / |v|)`.
4. Return True iff `yaw_min ≤ yaw ≤ yaw_max` AND `pitch_min ≤ pitch ≤ pitch_max`.

Emitters with no arc setters (torpedo tubes) fall back to the existing `dot(direction_world, aim_world) > 0` 90° cone.

### 2. Multi-bank fire

**File:** `engine/appc/subsystems.py`

`PhaserSystem` overrides `StartFiring(target, offset)`. Instead of WeaponSystem's "fire first eligible bank then return" round-robin:

```python
def StartFiring(self, target=None, offset=None):
    if not self.IsOn() or target is None: return
    ship = self.GetParentShip()
    aim_world = _resolve_aim_world(ship, target)
    for i in range(self.GetNumWeapons()):
        bank = self.GetWeapon(i)
        if not _emitter_in_arc(bank, ship, aim_world): continue
        if hasattr(bank, "CanFire") and bank.CanFire():
            bank.Fire(target, offset)
            self._currently_firing.append(i)
```

`StopFiring()` already calls `StopFiring` on each bank in `_currently_firing` — keep as-is.

### 3. Continuous damage tick

**File:** `engine/host_loop.py` (extend `_advance_combat`)

After the existing torpedo-hit loop, walk every ship's PhaserSystem:

```python
for ship in ships_list:
    sys = ship.GetPhaserSystem()
    if sys is None: continue
    for i in range(sys.GetNumWeapons()):
        bank = sys.GetWeapon(i)
        if not bank.IsFiring(): continue
        target = bank._target
        if target is None or target.IsDead():
            bank.StopFiring(); continue
        emitter_pos = bank._emitter_world_position()
        target_sub  = ship.GetTargetSubsystem() if hasattr(ship, "GetTargetSubsystem") else None
        target_pos  = (target_sub or target).GetWorldLocation()
        # Arc re-check — if target drifted out, auto-stop this bank.
        if not _emitter_in_arc(bank, ship, _normalize(target_pos − emitter_pos)):
            bank.StopFiring(); continue
        dist = |target_pos − emitter_pos|
        max_dist = bank.GetProperty().GetMaxDamageDistance()
        max_dmg  = bank.GetProperty().GetMaxDamage()
        damage = max_dmg * max(0.0, 1.0 − dist / max_dist) * dt
        if damage > 0:
            apply_hit(target, damage, target_pos, source=ship, subsystem=target_sub)
            # shield_hit is fired inside apply_hit's existing path via the
            # post-PR-2b wiring; no new code here.
```

### 4. Charge tweak

**File:** `engine/appc/subsystems.py`

In `_EnergyWeaponFireMixin.UpdateCharge`, change the auto-stop threshold:

```python
if self._firing:
    self._charge_level = max(0.0, self._charge_level - self._normal_discharge_rate * dt)
    if self._charge_level < self._min_firing_charge:
        self._firing = False
```

(Currently stops at `<= 0`; the cleaner gate is "drops below the minimum required to fire". Matches CanFire's threshold.)

### 5. Phaser render pass

**Files:** `native/src/renderer/include/renderer/frame.h`, `native/src/renderer/phaser_pass.{cc,h}`, `native/src/renderer/shaders/phaser.{vert,frag}`, `native/src/renderer/CMakeLists.txt`, `native/src/renderer/pipeline.{cc,h}`.

New descriptor:

```cpp
struct PhaserBeamDescriptor {
    glm::vec3 emitter_world;
    glm::vec3 target_world;
    glm::vec4 color;     // RGBA additive
    float     width;     // world-units half-width of the beam quad
};
```

`PhaserPass::render(beams, camera, pipeline)`:

- Vertex shader builds a quad per beam: two vertices at emitter, two at target, offset perpendicular to the camera→beam axis vector by ±`width`. (Same camera-aligned billboard trick as torpedoes, but stretched along the beam axis.)
- Fragment shader samples `data/Textures/Tactical/PhaserLights.tga` along the beam, tints by `u_color`. Alpha shaped by U-axis (so beam fades softly at endpoints).
- GL state: additive blend (`SRC_ALPHA, ONE`), depth test on, depth write off. Render after torpedoes, before dust.

Texture cache mirrors `TorpedoPass` — single shared texture handle.

### 6. Host binding + Python wiring

**Files:** `native/src/host/host_bindings.cc`, `engine/host_loop.py`, `engine/renderer.py`.

`host.set_phaser_beams(list[dict])` mirroring `set_torpedoes`. Each dict carries `{position, target, color, width}`.

`host_loop._build_phaser_beam_data()` walks ships' PhaserSystem banks and yields one entry per firing bank (emitter_world from `bank._emitter_world_position()`, target_world from the bank's `_target.GetWorldLocation()` plus optional subsystem offset).

Push the list each tick from `_advance_combat`, after the damage tick.

### 7. Sound discipline

**File:** `engine/appc/subsystems.py` (PhaserBank.Fire / StopFiring).

- `Fire()`: existing `_play_fire_sfx` plays `<name> Start` (already in place — falls back to bare `<name>` if Start is missing).
- `StopFiring()`: new — play `<name> Stop`. Best-effort; if the sound doesn't exist, no-op.
- Loop sound (`<name> Loop`) is out of PR 2c scope. Would require looping-sound infrastructure in TGSoundManager.

### 8. Input wiring

**File:** `engine/host_loop.py` (`_poll_mouse_buttons`).

Restore LBUTTON forwarding (PR 2b dropped it). KeyDown → `App.g_kInputManager.OnKeyDown(WC_LBUTTON)` flows through the existing input chain → `ET_INPUT_FIRE_PHASER` → `TacticalInterfaceHandlers.FireWeapons` → `player.GetPhaserSystem().StartFiring(player.GetTarget())`. KeyUp → `StopFiring()`.

### 9. Charging + alert gating (inherited)

No new code; documenting the chain:

- **Alert gate**: PhaserSystem inherits `PoweredSubsystem`. PR 2a wires `_powered_on` to alert level. At GREEN, `IsOn()` returns False, multi-bank fire never starts.
- **Charge gate**: `PhaserBank.CanFire()` returns True only when `parent.IsOn() AND _charge_level >= _min_firing_charge`.
- **Per-frame charge tick**: `_advance_weapons` walks every emitter and calls `UpdateCharge(dt)`. Drains while firing, recharges while idle if parent is on.

Galaxy values: MaxCharge=5.0, MinFiringCharge=3.0, NormalDischargeRate=1.0/s, RechargeRate=0.08/s. A full bank sustains ~2 s of continuous fire; full recharge takes ~25 s. Recharge is intentionally slow so banks rotate naturally across a sustained engagement.

## Testing

### Unit (engine)

- `test_arc_gate.py` — target dead-center accepted; target just inside accepted; target just outside rejected on each of the four arc bounds (yaw min/max, pitch min/max); emitter with no arc setters falls back to dot > 0.
- `test_phaser_damage_falloff.py` — dist=0 → MaxDamage × dt; dist=MaxDamageDistance → 0; dist > max → 0; dist=half → MaxDamage × 0.5 × dt.
- `test_phaser_multi_bank_fire.py` — Galaxy at RED + target ahead → 4 forward-arc banks fire simultaneously; 4 aft-arc banks don't. Banks with `_charge_level < min_firing_charge` skipped.
- `test_phaser_charge_stops_fire.py` — bank firing sustained for 2.5 s on default Galaxy values → `_firing` flips to False once `_charge_level < min_firing_charge`; after release, recharge resumes.

### Integration (existing pytest harness)

- `test_phaser_fire_chain_galaxy.py` — LBUTTON down → StartFiring runs → multi-bank fire → release → all banks stopped. Mocks sound.
- `test_phaser_no_fire_at_green_alert.py` — Galaxy at GREEN + LBUTTON-down → no bank goes `_firing`.
- `test_phaser_target_drifts_out_of_arc.py` — start firing → reposition target outside arc → next tick auto-stops the bank → other banks continue.
- `test_phaser_damage_applied_through_apply_hit.py` — assert target's shield/hull condition decreases over a held-fire tick using mocked combat.apply_hit.

### Visual smoke test

Built binary; mission with player Galaxy + target; RED alert; hold LBUTTON. Expectations:
- Multiple beams visible from saucer + engineering hardpoints.
- Shield bubble splashes at impact point for each frame's hit.
- Sound plays once on press, again on release.
- Banks drop out as charge depletes; recharge visible when released.

## Out of scope

- AI ships returning fire (deferred to PR 2d or later).
- PulseWeapon (Vor'cha / Marauder discrete bolts).
- TractorBeam (visual + pull-target physics).
- Looping "X Loop" sounds.
- Cursor-aim free-fire mode.
- Multi-target spread fire.

## Open questions

None. Beam color, width, and texture all read from sensible defaults: `PhaserLights.tga` exists in `game/data/Textures/Tactical/`; color is faction-conventional Federation amber (1.0, 0.6, 0.2, 1.0) hardcoded for the player Galaxy and parameterized for later PRs; width is a small constant (~0.05 world units) tunable in the descriptor.

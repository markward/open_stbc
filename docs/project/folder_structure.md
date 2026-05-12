# open_stbc — Project Folder Structure

## Overview

```
open_stbc/
│
├── game/                          # Local BC installation (gitignored)
│   ├── scripts/                   # Original BC Python scripts
│   ├── data/                      # Models, textures, animations
│   │   ├── Models/
│   │   ├── TGL/
│   │   └── animations/
│   ├── sfx/                       # Audio assets
│   │   ├── Weapons/
│   │   └── Explosions/
│   └── *.exe                      # Original BC executables
│
├── sdk/                           # BC SDK v1.1 (gitignored)
│   ├── scripts/                   # SDK Python source — reference and
│   │   ├── AI/                    # integration test ground truth
│   │   ├── Bridge/
│   │   ├── Conditions/
│   │   ├── Maelstrom/
│   │   ├── ships/
│   │   │   └── Hardpoints/
│   │   ├── Systems/
│   │   ├── Tactical/
│   │   ├── App.py                 # SWIG-generated Appc interface spec
│   │   ├── MissionLib.py
│   │   └── GlobalPropertyTemplates.py
│   └── docs/                      # SDK HTML documentation
│
├── engine/                        # Phase 1: Python Appc shim
│   ├── __init__.py
│   ├── appc/                      # Appc interface reimplementation
│   │   ├── __init__.py
│   │   ├── objects.py             # ObjectClass, PhysicsObjectClass etc
│   │   ├── ships.py               # ShipClass, subsystems
│   │   ├── sets.py                # SetClass, SetManager
│   │   ├── events.py              # TGEvent, TGEventManager
│   │   ├── timers.py              # TGTimer, TGTimerManager
│   │   ├── sequences.py           # TGSequence, TGAction types
│   │   ├── ai.py                  # ArtificialIntelligence base classes
│   │   ├── characters.py          # CharacterClass, CharacterAction
│   │   └── constants.py           # ET_ event types, enums
│   ├── physics/                   # Physics integration
│   │   ├── __init__.py
│   │   └── simulation.py          # PyBullet wrapper (Phase 1)
│   ├── events/                    # Event system
│   │   ├── __init__.py
│   │   ├── manager.py             # g_kEventManager implementation
│   │   └── broadcast.py           # Broadcast handler registry
│   ├── spatial/                   # Spatial queries
│   │   ├── __init__.py
│   │   ├── proximity.py           # ProximityCheck, ProximityManager
│   │   └── raycast.py             # GetLineIntersectObjects
│   └── audio/                     # Audio system (stub in Phase 1)
│       ├── __init__.py
│       └── manager.py             # TGSound implementation
│
├── native/                        # Phase 2: C++ engine source
│   ├── src/
│   │   ├── main.cpp               # Entry point, game loop
│   │   ├── physics/
│   │   ├── audio/
│   │   ├── renderer/
│   │   └── python_embed/          # CPython embedding layer
│   ├── include/
│   └── CMakeLists.txt
│
├── tools/                         # Development and instrumentation
│   ├── __init__.py
│   ├── appc_logger.py             # Appc shim for live game capture
│   ├── asset_scanner.py           # Builds animation/asset manifests
│   ├── session_replay/            # Replay logged sessions against engine
│   │   ├── __init__.py
│   │   └── replayer.py
│   └── setup.py                   # Validates game installation
│
├── tests/
│   ├── __init__.py
│   ├── fixtures/                  # Logged sessions as test fixtures
│   ├── unit/                      # Unit tests per engine subsystem
│   │   ├── test_events.py
│   │   ├── test_physics.py
│   │   ├── test_spatial.py
│   │   └── test_sequences.py
│   └── integration/               # Full mission integration tests
│       └── tutorial/
│           ├── test_m1basic.py
│           ├── test_m2objects.py
│           └── test_m3gameflow.py
│
├── docs/
│   ├── gap_analysis.md            # Engine gap analysis
│   ├── open_questions.md          # Instrumentation investigation targets
│   ├── folder_structure.md        # This file
│   └── architecture/              # Subsystem design documents
│
├── .gitignore
├── pyproject.toml
├── CMakeLists.txt                 # Phase 2 build
└── README.md
```

## Hardcoded paths

The following paths are used throughout the project and assumed to be
present on every contributor's machine:

| Constant | Path | Contents |
|---|---|---|
| `BC_GAME_PATH` | `./game` | Original BC installation |
| `BC_SDK_PATH` | `./sdk` | BC SDK v1.1 |

## Gitignored directories

```
# .gitignore
game/
sdk/
```

## Setup

Drop your BC installation into `game/` and your BC SDK into `sdk/`.
Then:

```bash
uv sync
uv run pytest
```


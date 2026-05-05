# open_stbc

Open reimplementation of the Bridge Commander engine.

## Legal notice

This project is an independent engine reimplementation. It does not include any game assets, scripts, or content from Star Trek: Bridge Commander. A legitimate retail copy of Star Trek: Bridge Commander is required to use this software.

This project is not made by, affiliated with, or supported by Activision or Paramount.

## Setup

Drop your BC installation into `game/` and your BC SDK into `sdk/`.

```bash
uv sync
uv run pytest
```

See `docs/gap_analysis.md` for the engine gap analysis and implementation phases.

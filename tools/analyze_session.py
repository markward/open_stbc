"""Analyze a BCTickLog.cfg session and report tick rate (Q1) and time scale (Q3)."""
import pathlib
import statistics
import sys

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_LOG = PROJECT_ROOT / "game" / "BCTickLog.cfg"


def read_log(log_path: pathlib.Path) -> list[tuple[float, int, float]]:
    """Parse the [BCTickLog] section from a SaveConfigFile-format .cfg file."""
    if not log_path.exists():
        print(f"Log not found: {log_path}")
        print("Run setup.py --recompile, play Quick Battle for 30s, then retry.")
        sys.exit(1)

    tick_data: dict[int, str] = {}
    count = 0
    in_section = False

    with open(log_path) as f:
        for line in f:
            line = line.rstrip("\r\n")
            if line == "[BCTickLog]":
                in_section = True
                continue
            if line.startswith("[") and in_section:
                break
            # Config format uses = for strings, | for ints — handle both.
            sep = "=" if "=" in line else "|" if "|" in line else ""
            if not in_section or not sep:
                continue
            key, _, val = line.partition(sep)
            if key == "count":
                count = int(val)
            elif key in ("err_type", "err_value"):
                print(f"Snippet error recorded: {key}={val}")
            elif key.startswith("t") and key[1:].isdigit():
                tick_data[int(key[1:])] = val

    entries: list[tuple[float, int, float]] = []
    for i in range(count):
        raw = tick_data.get(i, "")
        parts = raw.split()
        if len(parts) == 3:
            entries.append((float(parts[0]), int(parts[1]), float(parts[2])))
    return entries


def analyze(log_path: pathlib.Path) -> None:
    entries = read_log(log_path)

    if len(entries) < 10:
        print(f"Only {len(entries)} entries — need at least 10.")
        print("Make sure gameplay was active (Quick Battle, not just the main menu).")
        sys.exit(1)

    wall = [e[0] for e in entries]
    frames = [e[1] for e in entries]
    game_t = [e[2] for e in entries]

    total_wall = wall[-1] - wall[0]
    total_frames = frames[-1] - frames[0]
    mean_hz = total_frames / total_wall
    period_ms = (total_wall / total_frames) * 1000

    frame_steps = [frames[i + 1] - frames[i] for i in range(len(frames) - 1)]
    skipped = sum(1 for s in frame_steps if s > 1)

    game_duration = game_t[-1] - game_t[0]
    time_scale = game_duration / total_wall

    print(f"Samples:    {len(entries)} frame boundaries")
    print(f"Duration:   {total_wall:.1f}s wall / {game_duration:.1f}s game time")
    print(f"Frames:     {total_frames} ticks")
    print(f"Tick rate:  {mean_hz:.2f} Hz  ({period_ms:.2f} ms/tick)")

    if len(frame_steps) > 1:
        wall_deltas = [wall[i + 1] - wall[i] for i in range(len(wall) - 1)]
        sample_sigma = statistics.stdev(wall_deltas) * 1000
        print(f"Sample σ:   {sample_sigma:.2f} ms (includes AI scheduling jitter)")

    print(f"Time scale: {time_scale:.4f}  (1.000 = normal speed)")

    if skipped:
        pct = 100.0 * skipped / len(frame_steps)
        print(f"Note:       {skipped}/{len(frame_steps)} samples ({pct:.0f}%) skipped frames")
        print("            Python not called every tick - tick rate above is still accurate.")

    print()
    for candidate_hz in (20, 25, 30, 60):
        if abs(period_ms - 1000.0 / candidate_hz) < 2.0:
            print(f"Q1 answer:  {candidate_hz} Hz fixed tick rate")
            return

    if mean_hz < 5:
        print(f"Q1 answer:  {mean_hz:.1f} Hz - unexpectedly low, check gameplay was active")
    else:
        wall_deltas = [wall[i + 1] - wall[i] for i in range(len(wall) - 1)]
        verdict = "fixed" if statistics.stdev(wall_deltas) * 1000 < 3.0 else "variable"
        print(f"Q1 answer:  {mean_hz:.1f} Hz ({verdict})")


if __name__ == "__main__":
    log = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    analyze(log)

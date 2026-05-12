import App

from engine.appc.ship_iter import iter_ships

TICK_RATE = 60
TICK_DELTA = 1.0 / TICK_RATE


class GameLoop:
    """Drives App.g_kTimerManager, App.g_kRealtimeTimerManager, and live-ship
    subsystem updates at 60 Hz.

    Phase 1: both timer managers advance at the same fixed rate.
    Subsystem updates run after timers, mirroring the instrumented
    AI/Python-first-then-physics-then-render ordering (Q2).
    """

    def tick(self) -> None:
        App.g_kTimerManager.tick(TICK_DELTA)
        App.g_kRealtimeTimerManager.tick(TICK_DELTA)
        for ship in iter_ships():
            ss = ship.GetShieldSubsystem()
            if ss is not None:
                ss.Update(TICK_DELTA)

    def advance(self, n: int) -> None:
        for _ in range(n):
            self.tick()

    @property
    def game_time(self) -> float:
        return App.g_kTimerManager.get_time()

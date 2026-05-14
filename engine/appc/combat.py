"""Combat collision + damage routing — Task 2 stub.

Task 5 replaces with the full implementation (pick_target_subsystem
walks subsystem tree; apply_hit routes shields → subsystem → hull).
For now sphere_hit is correct and pick_target_subsystem returns hull.
"""
from engine.appc.math import TGPoint3


def sphere_hit(point: TGPoint3, center: TGPoint3, radius: float) -> bool:
    """Point-in-sphere test using squared distance (no sqrt)."""
    dx = point.x - center.x
    dy = point.y - center.y
    dz = point.z - center.z
    r = float(radius)
    return (dx * dx + dy * dy + dz * dz) <= r * r


def pick_target_subsystem(ship, hit_point):
    """Stub for Task 2; Task 5 walks the subsystem tree."""
    return ship.GetHull() if hasattr(ship, "GetHull") else None

"""§3.3 — Resource capacity slack on top of CPM critical path (calendars / crews heuristic)."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from azraq_mc.cpm import critical_path_months_batch, task_durations_matrix
from azraq_mc.schemas import CpmResourcePool, CpmTaskSpec


def critical_path_months_with_resources(
    tasks: Sequence[CpmTaskSpec],
    pools: Sequence[CpmResourcePool],
    z: np.ndarray,
    factor_order: tuple[str, ...],
) -> np.ndarray:
    """
    Add contention months when resource demand on the critical chain exceeds pool capacity.
    If pools empty, falls back to vanilla critical path.
    """
    base = critical_path_months_batch(tasks, z, factor_order)
    if not pools:
        return base
    durs = task_durations_matrix(tasks, z, factor_order)
    n = durs.shape[0]
    cap = {p.resource_id: max(p.capacity_units * p.calendar_efficiency, 1e-9) for p in pools}
    extra = np.zeros(n, dtype=np.float64)
    for i in range(n):
        load: dict[str, float] = {}
        for j, t in enumerate(tasks):
            if t.resource_id is None:
                continue
            load[t.resource_id] = load.get(t.resource_id, 0.0) + float(durs[i, j]) * t.resource_units
        slack = 0.0
        for rid, lam in load.items():
            c = cap.get(rid)
            if c is None:
                continue
            if lam > c:
                bases = [t.duration_base_months for t in tasks if t.resource_id == rid]
                dbase = float(np.mean(bases)) if bases else 1.0
                slack += (lam - c) / c * dbase * 0.25
        extra[i] = slack
    return base + extra

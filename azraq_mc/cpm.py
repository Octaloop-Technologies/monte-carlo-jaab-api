"""§3.3 — Project CPM / critical path from a task DAG (stochastic durations from shocks)."""
from __future__ import annotations

from collections import deque
from collections.abc import Sequence

import numpy as np

from azraq_mc.schemas import CpmTaskSpec


def _task_index_map(tasks: Sequence[CpmTaskSpec]) -> dict[str, int]:
    mp = {t.task_id: i for i, t in enumerate(tasks)}
    if len(mp) != len(tasks):
        raise ValueError("duplicate task_id in cpm_tasks")
    return mp


def _topological_completion_order(tasks: Sequence[CpmTaskSpec]) -> list[int]:
    """Kahn topological sort; raises if cycle or missing predecessor."""
    tid_to_i = _task_index_map(tasks)
    n = len(tasks)
    indeg = [0] * n
    adj: list[list[int]] = [[] for _ in range(n)]
    for j, t in enumerate(tasks):
        for p in t.predecessor_ids:
            if p not in tid_to_i:
                raise ValueError(f"unknown predecessor {p!r} for task {t.task_id!r}")
            i = tid_to_i[p]
            adj[i].append(j)
            indeg[j] += 1
    q = deque(i for i in range(n) if indeg[i] == 0)
    out: list[int] = []
    while q:
        u = q.popleft()
        out.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(out) != n:
        raise ValueError("cpm_tasks contains a cycle or disconnected graph")
    return out


def task_durations_matrix(
    tasks: Sequence[CpmTaskSpec],
    z: np.ndarray,
    factor_order: tuple[str, ...],
) -> np.ndarray:
    """
    Per-scenario task durations in months: shape (n_scenarios, n_tasks).
    z is (n_scenarios, n_factors) or broadcast last dim averaged for 3d.
    """
    z2 = np.asarray(z, dtype=np.float64)
    if z2.ndim == 3:
        z2 = np.mean(z2, axis=2)
    n = z2.shape[0]
    idx = {name: i for i, name in enumerate(factor_order)}
    durs = np.zeros((n, len(tasks)), dtype=np.float64)
    for j, t in enumerate(tasks):
        d = np.full(n, t.duration_base_months, dtype=np.float64)
        for link in t.shock_links:
            if link.factor_id not in idx:
                raise ValueError(f"cpm task {t.task_id}: unknown factor {link.factor_id!r}")
            col = idx[link.factor_id]
            contrib = link.months_per_positive_z * np.maximum(0.0, z2[:, col])
            d += contrib
        durs[:, j] = d
    return durs


def critical_path_months_batch(
    tasks: Sequence[CpmTaskSpec],
    z: np.ndarray,
    factor_order: tuple[str, ...],
) -> np.ndarray:
    """
    For each scenario, longest path (months) in the CPM DAG using task durations.
    Returns shape (n_scenarios,).
    """
    if not tasks:
        raise ValueError("cpm_tasks must be non-empty for CPM mode")
    order = _topological_completion_order(tasks)
    tid_to_i = _task_index_map(tasks)
    n_tasks = len(tasks)
    durs = task_durations_matrix(tasks, z, factor_order)
    pred_lists = [[tid_to_i[p] for p in t.predecessor_ids] for t in tasks]

    n_scen = durs.shape[0]
    finish = np.zeros((n_scen, n_tasks), dtype=np.float64)
    for j in order:
        preds = pred_lists[j]
        if not preds:
            start = 0.0
        else:
            start = np.max(finish[:, preds], axis=1)
        finish[:, j] = start + durs[:, j]
    # sink(s): max finish among tasks with no outgoing edge
    outgoing = [0] * n_tasks
    for t in tasks:
        for p in t.predecessor_ids:
            outgoing[tid_to_i[p]] += 1
    sinks = [i for i in range(n_tasks) if outgoing[i] == 0]
    if not sinks:
        sinks = list(range(n_tasks))
    return np.max(finish[:, sinks], axis=1)

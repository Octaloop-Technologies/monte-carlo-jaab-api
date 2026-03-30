from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from azraq_mc.schemas import ShockArray, ShockPackSpec


def save_shockpack_npz(
    directory: Path | str,
    spec: ShockPackSpec,
    shocks: ShockArray,
    *,
    filename_prefix: str | None = None,
) -> Path:
    """
    Persist shock matrix + spec metadata (stand-in for Parquet/MinIO artifacts).
    Returns path to the .npz file.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    prefix = filename_prefix or f"{spec.shockpack_id}_{spec.seed}_{spec.n_scenarios}"
    meta_path = directory / f"{prefix}_meta.json"
    npz_path = directory / f"{prefix}_z.npz"
    z = np.asarray(shocks.z, dtype=np.float64)
    meta = {
        "shockpack": spec.model_dump(mode="json"),
        "shock_array": {
            "shockpack_id": shocks.shockpack_id,
            "seed": shocks.seed,
            "n_scenarios": shocks.n_scenarios,
            "factor_order": list(shocks.factor_order),
        },
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    np.savez_compressed(npz_path, z=z)
    return npz_path

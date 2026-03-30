"""Semantic versions for audit / incremental recompute metadata (conceptual layer IDs)."""

SHOCK_LAYER_VERSION = "1.1.0"
TRANSFORM_LAYER_VERSION = "1.0.0"
METRICS_LAYER_VERSION = "1.1.0"
IMPACT_MODEL_VERSION = "2.0.0"


def layer_versions_bundle() -> dict[str, str]:
    return {
        "shock_layer": SHOCK_LAYER_VERSION,
        "transform_layer": TRANSFORM_LAYER_VERSION,
        "impact_model": IMPACT_MODEL_VERSION,
        "metrics_layer": METRICS_LAYER_VERSION,
    }

from __future__ import annotations

from azraq_mc.schemas import ShockPackSpec
from azraq_mc.shockpack_catalog import load_entry


def resolve_shockpack_for_request(
    shockpack: ShockPackSpec | None,
    catalog_entry_id: str | None,
) -> tuple[ShockPackSpec, str | None]:
    if catalog_entry_id:
        sp = ShockPackSpec.model_validate(load_entry(catalog_entry_id)["spec"])
        if shockpack is not None:
            sp = sp.model_copy(update=shockpack.model_dump(exclude_unset=True))
        return sp, catalog_entry_id
    if shockpack is None:
        raise ValueError("shockpack is required when shockpack_catalog_entry_id is not set")
    return shockpack, None

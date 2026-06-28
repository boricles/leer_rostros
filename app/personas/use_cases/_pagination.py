"""Pagination helpers for persona use cases."""

from math import ceil

from app.schemas import PaginationMeta
from app.shared._helpers import LIMITE_MAX


def normalize_pagination(
    *,
    limite: int,
    offset: int = 0,
    page: int | None = None,
) -> tuple[int, int]:
    """Clamp limit and resolve page/offset into a non-negative offset."""
    limit = max(1, min(LIMITE_MAX, limite))
    if page is not None:
        current_page = max(1, page)
        return limit, (current_page - 1) * limit
    return limit, max(0, offset)


def build_pagination_meta(
    *,
    total_records: int,
    limit: int,
    offset: int,
) -> PaginationMeta:
    """Build response pagination metadata from total, limit, and offset."""
    safe_total = max(0, total_records)
    total_pages = ceil(safe_total / limit) if safe_total else 0
    current_page = (offset // limit) + 1
    return PaginationMeta(
        total_records=safe_total,
        current_page=current_page,
        total_pages=total_pages,
        limit=limit,
        offset=offset,
    )

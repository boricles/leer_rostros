"""Matching policy: single source of truth for thresholds and confidence."""

from dataclasses import dataclass
from typing import Literal

# Type alias for confidence bands
Confianza = Literal["alta", "media", "baja"]


@dataclass(frozen=True)
class MatchingPolicy:
    """Single source of truth for match decisions.

    Loaded from Settings.match_threshold at app startup.
    Confidence bands are class defaults calibrated for InsightFace buffalo_l.
    match_percentage delegates to faces.distance_to_confidence (sigmoid).
    """

    threshold: float
    conf_alta: float = 0.40
    conf_media: float = 0.55

    def is_match(self, distance: float) -> bool:
        """True iff distance < self.threshold (strict <)."""
        return distance < self.threshold

    def confidence_band(self, distance: float) -> Confianza:
        """Return 'alta', 'media', or 'baja' based on configured bands.

        - 'alta' if distance < conf_alta (0.40)
        - 'media' if distance < conf_media (0.55)
        - 'baja' otherwise
        """
        if distance < self.conf_alta:
            return "alta"
        if distance < self.conf_media:
            return "media"
        return "baja"

    def match_percentage(self, distance: float) -> int:
        """0-100 percentage via sigmoid in faces.distance_to_confidence.

        Sigmoid calibrated for InsightFace buffalo_l (k=12.0, midpoint=0.40).
        Replaces the old 1.2 divisor from Facenet512 era.

        Testing note: This method delegates to faces.distance_to_confidence.
        To test without loading InsightFace, mock that function in tests.
        """
        # Lazy import to avoid loading InsightFace at module import time
        from app import faces

        return int(faces.distance_to_confidence(distance))

from __future__ import annotations

import enum


class AgentSelectionPolicy(str, enum.Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    TAG_MATCH = "tag_match"


__all__ = ["AgentSelectionPolicy"]

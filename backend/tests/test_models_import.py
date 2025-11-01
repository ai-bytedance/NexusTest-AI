from __future__ import annotations

import importlib
import sys


def test_models_import_smoke() -> None:
    """Ensure importing the models package triggers mapper configuration."""

    for name in list(sys.modules):
        if name == "app.models" or name.startswith("app.models."):
            sys.modules.pop(name)

    module = importlib.import_module("app.models")

    assert hasattr(module, "Agent"), "Expected Agent model to be available after import"

    agent_model = getattr(module, "Agent")
    assert getattr(agent_model, "__tablename__", None) == "agents"

from __future__ import annotations

import importlib
import sys
from typing import Any

from sqlalchemy.orm import DeclarativeBase


def test_models_import_smoke() -> None:
    """Ensure importing the models package triggers mapper configuration."""

    for name in list(sys.modules):
        if name == "app.models" or name.startswith("app.models."):
            sys.modules.pop(name)

    module = importlib.import_module("app.models")

    assert hasattr(module, "Agent"), "Expected Agent model to be available after import"

    agent_model = getattr(module, "Agent")
    assert getattr(agent_model, "__tablename__", None) == "agents"


def test_no_reserved_metadata_attributes() -> None:
    """Ensure no model defines a reserved 'metadata' Python attribute.
    
    This test prevents regression of the SQLAlchemy InvalidRequestError:
    'Attribute name 'metadata' is reserved'. Models should use 'metadata_'
    as the Python attribute name with 'metadata' as the column name.
    """
    # Clear any existing imports to ensure fresh loading
    for name in list(sys.modules):
        if name == "app.models" or name.startswith("app.models."):
            sys.modules.pop(name)

    # Import the models module
    import app.models as models_module
    
    # Check all model classes for reserved metadata attributes
    reserved_attrs_found = []
    
    for attr_name in dir(models_module):
        attr = getattr(models_module, attr_name)
        
        # Check if it's a model class (inherits from Base and has __tablename__)
        if (
            isinstance(attr, type) 
            and issubclass(attr, DeclarativeBase)
            and hasattr(attr, '__tablename__')
        ):
            # Check if the model has a 'metadata' attribute (not 'metadata_')
            if hasattr(attr, 'metadata') and not hasattr(attr, 'metadata_'):
                # This could be the reserved SQLAlchemy metadata attribute
                # or a problematic custom attribute
                try:
                    # Try to access it - if it's the reserved attribute, this will fail
                    metadata_val = getattr(attr, 'metadata')
                    # If we get here, it might be a custom attribute, which is still problematic
                    if not callable(metadata_val) and not hasattr(metadata_val, 'mapped'):
                        reserved_attrs_found.append(f"{attr_name}.metadata")
                except Exception:
                    # Expected for the reserved attribute - this is what we're trying to prevent
                    reserved_attrs_found.append(f"{attr_name}.metadata")
    
    assert not reserved_attrs_found, (
        f"Found reserved 'metadata' attributes on models: {reserved_attrs_found}. "
        "Use 'metadata_' as the Python attribute name with 'metadata' as the column name."
    )

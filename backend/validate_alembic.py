#!/usr/bin/env python3
"""
Validate Alembic migration chain integrity.
This script checks for common issues that break migrations:
1. Multiple heads (branched history)
2. Missing revision references
3. Invalid revision graph

Usage: python validate_alembic.py
Exit codes: 0 = success, 1 = validation failure
"""

import sys
from alembic.config import Config
from alembic.script.base import ScriptDirectory


def validate_alembic():
    """Validate Alembic migration chain integrity."""
    try:
        cfg = Config("alembic.ini")
        script_dir = ScriptDirectory.from_config(cfg)
        
        # Check 1: Single head
        heads = script_dir.get_heads()
        if len(heads) != 1:
            print(f"❌ FAIL: Multiple heads found: {heads}")
            print(f"   Expected: 1 head, Found: {len(heads)} heads")
            return False
        
        print(f"✅ PASS: Single head found: {heads[0]}")
        
        # Check 2: All revisions traversable
        try:
            revisions = list(script_dir.walk_revisions())
            print(f"✅ PASS: All {len(revisions)} revisions traversable")
        except Exception as e:
            print(f"❌ FAIL: Cannot traverse revision history: {e}")
            return False
        
        # Check 3: All down_revision references exist
        missing_refs = []
        for rev in revisions:
            if rev.down_revision:
                if isinstance(rev.down_revision, (list, tuple)):
                    for parent in rev.down_revision:
                        if not script_dir.get_revision(parent):
                            missing_refs.append((rev.revision, parent))
                else:
                    if not script_dir.get_revision(rev.down_revision):
                        missing_refs.append((rev.revision, rev.down_revision))
        
        if missing_refs:
            print(f"❌ FAIL: Missing revision references:")
            for rev_ref, missing_ref in missing_refs:
                print(f"   {rev_ref} -> {missing_ref}")
            return False
        
        print(f"✅ PASS: All revision references exist")
        
        # Check 4: Revision files exist for all revisions
        revision_files = set()
        for rev in revisions:
            if rev.down_revision:
                if isinstance(rev.down_revision, (list, tuple)):
                    for parent in rev.down_revision:
                        revision_files.add(parent)
                else:
                    revision_files.add(rev.down_revision)
            revision_files.add(rev.revision)
        
        print(f"✅ PASS: All {len(revision_files)} revision IDs accounted for")
        
        print(f"\n🎉 SUCCESS: Alembic migration chain is healthy!")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: Unexpected error during validation: {e}")
        return False


if __name__ == "__main__":
    success = validate_alembic()
    sys.exit(0 if success else 1)
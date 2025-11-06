#!/usr/bin/env sh
set -euo pipefail
python - <<'PY'
import importlib, sys
mods = [
    'app.api.routes',
    'app.api.routes.importers',
    'app.api.routes.webhooks',
    'app.services',
]
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        print(f'IMPORT_FAIL {m}: {e}')
        sys.exit(1)
print('IMPORT_OK')
PY

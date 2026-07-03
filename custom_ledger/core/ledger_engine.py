# Copyright (c) 2026, Custom Ledger Contributors
# License: TBD. See license.txt
"""Backward-compatibility shim.

The Value Snapshot engine moved to ``engine_value_snapshot`` in PR #6.
This module re-exports the public hook entry points so any pre-PR-6 code
or stale cached references continue to work for one release.

Will be removed in a future cleanup PR. New code should import from
``custom_ledger.core.engine_value_snapshot`` directly.
"""

from custom_ledger.core.engine_value_snapshot import (  # noqa: F401
    capture_change,
    invalidate_config_cache,
)

# Copyright (c) 2026, Custom Ledger Contributors
# License: TBD. See license.txt
"""Cache utilities for the Custom Ledger engine.

The engine relies on Redis to cache "which Ledger Configs are active for this
DocType" — a per-save lookup that needs to be near-zero cost. After a deploy,
that cache can be stale (e.g. controller logic changed but cached values are
from the previous deploy). We clear it via the ``after_migrate`` hook below.
"""

import frappe

ENGINE_CACHE_PREFIX = "custom_ledger:configs_for:"


def clear_engine_cache(*args, **kwargs):
    """Clear all Custom Ledger engine caches.

    Wired into the ``after_migrate`` hook so it runs after every ``bench
    migrate``. Also safe to call manually from a console.

    Accepts arbitrary args/kwargs because Frappe's hook dispatchers vary
    slightly across versions — being tolerant avoids a fragile signature.
    """
    frappe.cache().delete_keys(ENGINE_CACHE_PREFIX + "*")
    frappe.clear_cache(doctype="Ledger Config")

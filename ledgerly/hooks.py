app_name = "ledgerly"
app_title = "Ledgerly"
app_publisher = "Ledgerly Contributors"
app_description = "Configurable custom ledgers for Frappe — define your own ledgers driven by field changes on any DocType."
app_email = "ledgerly@example.com"
app_license = "TBD"

# Document Events
# ---------------
# The wildcard "*" entry fires on every doc save in the system. The engine's
# first action is a cached lookup that returns immediately for DocTypes with
# no Ledger Config — so the per-save overhead is a single Redis hit.
#
# Ledger Config events keep the cache fresh: when a config is saved or deleted,
# we invalidate the cached active-config list for its source_doctype.
#
# Both engines (Value Snapshot today, Transactional in PR #9) hook into the
# same wildcard event. Each engine filters internally for the ledger types it
# handles, so they coexist without interfering.
doc_events = {
    "*": {
        "on_update": "ledgerly.core.engine_value_snapshot.capture_change",
        "on_submit": "ledgerly.core.engine_value_snapshot.capture_change",
        "on_load": "ledgerly.core.balance_recompute.recompute_on_load",
    },
    "Ledger Config": {
        "on_update": "ledgerly.core.engine_value_snapshot.invalidate_config_cache",
        "on_trash": "ledgerly.core.engine_value_snapshot.invalidate_config_cache",
    },
}

# Post-migrate hook
# -----------------
# Clear Ledgerly's engine cache after every ``bench migrate``. Prevents the
# "ledger entries stop being created after deploy" symptom that happens when
# Redis still holds pre-deploy active-config lookups.
after_migrate = ["ledgerly.core.cache_utils.clear_engine_cache"]

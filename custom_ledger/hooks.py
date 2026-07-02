app_name = "custom_ledger"
app_title = "Custom Ledger"
app_publisher = "Custom Ledger Contributors"
app_description = "Configurable custom ledgers for Frappe — define your own ledgers driven by field changes on any DocType."
app_email = "custom_ledger@example.com"
app_license = "TBD"

# Apps screen (v16 "iPhone-style" desktop) and app switcher.
# Routes to the Custom Ledger workspace. On v15 this is ignored harmlessly; the
# workspace itself provides the sidebar entry on both versions.
add_to_apps_screen = [
    {
        "name": "custom_ledger",
        "logo": "/assets/custom_ledger/images/custom-ledger-logo.svg",
        "title": "Custom Ledger",
        "route": "/app/custom-ledger",
    }
]

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
        "on_update": "custom_ledger.core.engine_value_snapshot.capture_change",
        "on_submit": [
            "custom_ledger.core.engine_value_snapshot.capture_change",
            "custom_ledger.core.engine_transactional.capture_submit",
        ],
        "before_cancel": "custom_ledger.core.engine_transactional.permit_feeder_cancel",
        "on_cancel": "custom_ledger.core.engine_transactional.capture_cancel",
        "on_load": "custom_ledger.core.balance_recompute.recompute_on_load",
    },
    "Ledger Config": {
        "on_update": [
            "custom_ledger.core.engine_value_snapshot.invalidate_config_cache",
            "custom_ledger.core.engine_transactional.invalidate_feeder_cache",
        ],
        "on_trash": [
            "custom_ledger.core.engine_value_snapshot.invalidate_config_cache",
            "custom_ledger.core.engine_transactional.invalidate_feeder_cache",
        ],
    },
    "Custom Field": {
        "before_delete": "custom_ledger.core.field_protection.block_if_referenced",
    },
}

# Post-migrate hook
# -----------------
# Clear Custom Ledger's engine cache after every ``bench migrate``. Prevents the
# "ledger entries stop being created after deploy" symptom that happens when
# Redis still holds pre-deploy active-config lookups.
after_migrate = [
    "custom_ledger.core.cache_utils.clear_engine_cache",
    "custom_ledger.core.engine_transactional.invalidate_feeder_cache",
]

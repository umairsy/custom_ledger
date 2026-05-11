app_name = "ledgerly"
app_title = "Ledgerly"
app_publisher = "Ledgerly Contributors"
app_description = "Configurable custom ledgers for Frappe — define your own ledgers driven by field changes on any DocType."
app_email = "ledgerly@example.com"
app_license = "TBD"

# required_apps = []

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/ledgerly/css/ledgerly.css"
# app_include_js = "/assets/ledgerly/js/ledgerly.js"

# include js, css files in header of web template
# web_include_css = "/assets/ledgerly/css/ledgerly.css"
# web_include_js = "/assets/ledgerly/js/ledgerly.js"

# Document Events
# ---------------
# The wildcard "*" entry fires on every doc save in the system. The engine's
# first action is a cached lookup that returns immediately for DocTypes with
# no Ledger Config — so the per-save overhead is a single Redis hit.
#
# Ledger Config events keep the cache fresh: when a config is saved or deleted,
# we invalidate the cached active-config list for its source_doctype.
doc_events = {
    "*": {
        "on_update": "ledgerly.core.ledger_engine.capture_change",
        "on_submit": "ledgerly.core.ledger_engine.capture_change",
    },
    "Ledger Config": {
        "on_update": "ledgerly.core.ledger_engine.invalidate_config_cache",
        "on_trash": "ledgerly.core.ledger_engine.invalidate_config_cache",
    },
}

# Scheduled Tasks
# ---------------
# scheduler_events = {}

# Testing
# -------
# before_tests = "ledgerly.tests.utils.before_tests"

# Fixtures
# --------
# fixtures = []

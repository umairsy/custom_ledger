# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt

import unittest

import frappe

from ledgerly.core.cache_utils import ENGINE_CACHE_PREFIX, clear_engine_cache


class TestCacheUtils(unittest.TestCase):
    """Sanity tests for the post-migrate cache clearer."""

    def test_clear_engine_cache_wipes_known_keys(self):
        frappe.cache().set_value(ENGINE_CACHE_PREFIX + "Test Source A", ["c1", "c2"])
        frappe.cache().set_value(ENGINE_CACHE_PREFIX + "Test Source B", "__none__")

        clear_engine_cache()

        self.assertIsNone(frappe.cache().get_value(ENGINE_CACHE_PREFIX + "Test Source A"))
        self.assertIsNone(frappe.cache().get_value(ENGINE_CACHE_PREFIX + "Test Source B"))

    def test_clear_engine_cache_tolerates_no_keys(self):
        clear_engine_cache()
        clear_engine_cache()  # Second call on empty cache must not raise.

    def test_clear_engine_cache_accepts_extra_args(self):
        """Hook dispatchers in different Frappe versions pass varying args."""
        clear_engine_cache("ignored", keyword="ignored")

# Copyright (c) 2026, Custom Ledger Contributors
# License: TBD. See license.txt

import unittest

import frappe


class TestSmoke(unittest.TestCase):
    """Verifies the Custom Ledger app installed correctly.

    These tests run after `bench install-app custom_ledger` and must pass before
    any feature PR is merged.
    """

    def test_module_registered(self):
        """Custom Ledger module should appear in Module Def after install."""
        modules = frappe.get_all("Module Def", filters={"app_name": "custom_ledger"}, pluck="name")
        self.assertIn("Custom Ledger", modules)

    def test_app_version_importable(self):
        """The app's __version__ should be importable and non-empty."""
        from custom_ledger import __version__

        self.assertTrue(__version__)
        self.assertIsInstance(__version__, str)

    def test_app_in_installed_apps(self):
        """custom_ledger should be listed in installed apps for the current site."""
        self.assertIn("custom_ledger", frappe.get_installed_apps())

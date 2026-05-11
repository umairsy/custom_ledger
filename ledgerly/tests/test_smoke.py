# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt

import unittest

import frappe


class TestSmoke(unittest.TestCase):
    """Verifies the Ledgerly app installed correctly.

    These tests run after `bench install-app ledgerly` and must pass before
    any feature PR is merged.
    """

    def test_module_registered(self):
        """Ledgerly module should appear in Module Def after install."""
        modules = frappe.get_all("Module Def", filters={"app_name": "ledgerly"}, pluck="name")
        self.assertIn("Ledgerly", modules)

    def test_app_version_importable(self):
        """The app's __version__ should be importable and non-empty."""
        from ledgerly import __version__

        self.assertTrue(__version__)
        self.assertIsInstance(__version__, str)

    def test_app_in_installed_apps(self):
        """ledgerly should be listed in installed apps for the current site."""
        self.assertIn("ledgerly", frappe.get_installed_apps())

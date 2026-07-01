"""Sphinx configuration for repoman API documentation."""

import sys
from pathlib import Path

# Make the repoman package importable without installing it
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

project = "repoman"
author = "Tecktron"
release = "0.1.0"
copyright = "2024, Tecktron"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

# GTK / GI imports are unavailable in the CI/doc-build environment (no display).
# List every GI namespace used across the codebase so autodoc can import modules
# without triggering gi.require_version() errors.
autodoc_mock_imports = [
    "gi",
    "gi.repository",
    "gi.repository.Adw",
    "gi.repository.Gdk",
    "gi.repository.GdkX11",
    "gi.repository.GLib",
    "gi.repository.Gio",
    "gi.repository.GObject",
    "gi.repository.Gtk",
    "gi.repository.PackageKitGlib",
    "gi.repository.Pango",
    "Xlib",
    "Xlib.display",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

html_theme = "furo"
html_title = "repoman — API Reference"

# autodoc defaults: show type annotations inline, preserve member order
autodoc_member_order = "bysource"
autodoc_typehints = "description"
add_module_names = False

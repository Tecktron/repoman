"""Sphinx configuration for repoman API documentation."""

import sys
from datetime import datetime
from pathlib import Path

# Make the repoman package importable without installing it
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

project = "Repoman"
author = "Tecktron"
release = "0.1.1"
copyright = f"{datetime.now().year}, Tecktron"

extensions = [
    "sphinx_conestack_theme",  # registers the "conestack" html_theme
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
    "debian",
    "debian.deb822",
    "requests",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

html_theme = "conestack"
html_title = "Repoman — API Reference"

html_theme_options = {
    "sidebar_right": True,
    "logo_url": "logo.png",
    "logo_title": "Repoman",
    "logo_width": "32px",
    "logo_height": "32px",
    "github_url": "https://github.com/Tecktron/repoman",
}

pygments_style = "rrt"

# Template override: forces data-bs-theme="dark" before conestack JS fires.
templates_path = ["_templates"]

# Custom CSS: project movie-poster palette layered over conestack's dark base
html_static_path = ["_static"]
html_css_files = ["custom.css"]

# autodoc defaults: show type annotations inline, preserve member order
autodoc_member_order = "bysource"
autodoc_typehints = "description"
add_module_names = False

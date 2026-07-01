"""Window positioning helpers for X11 / Xfwm4.

Post-map centering via python-xlib. Known limitation: a brief flicker
occurs because the WM places the window at its default position before
the move fires. Pre-realize positioning is the correct fix; deferred.
All public functions are no-ops on Wayland (GdkX11 / XID not available).
"""

from __future__ import annotations

import logging

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

_log = logging.getLogger(__name__)


def center_on_screen(window: Gtk.Window) -> None:
    """Center window on its monitor after it maps. Silently no-ops on Wayland."""
    window.connect("map", lambda w: GLib.idle_add(_center_on_screen_cb, w))


def center_on_parent(window: Gtk.Window) -> None:
    """Center window over its transient parent after it maps.
    Falls back to center-on-screen if parent position is unobtainable.
    Silently no-ops on Wayland."""
    window.connect("map", lambda w: GLib.idle_add(_center_on_parent_cb, w))


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


def _win_size(window: Gtk.Window) -> tuple[int, int]:
    """Return the window's allocated size, falling back to preferred natural size."""
    w, h = window.get_width(), window.get_height()
    if w == 0 or h == 0:
        w, h = window.get_default_size()
    # default_height=-1 means content-sized; measure natural preferred size instead
    if w <= 0 or h <= 0:
        _, nat = window.get_preferred_size()
        if w <= 0:
            w = nat.width
        if h <= 0:
            h = nat.height
    return w, h


def _center_on_screen_cb(window: Gtk.Window) -> bool:
    try:
        surface = window.get_surface()
        if surface is None:
            return GLib.SOURCE_REMOVE
        monitor = window.get_display().get_monitor_at_surface(surface)
        if monitor is None:
            return GLib.SOURCE_REMOVE
        geom = monitor.get_geometry()
        win_w, win_h = _win_size(window)
        x = geom.x + (geom.width - win_w) // 2
        y = geom.y + (geom.height - win_h) // 2
        _move(surface, x, y)
    except Exception:
        _log.debug("center_on_screen failed", exc_info=True)
    return GLib.SOURCE_REMOVE


def _center_on_parent_cb(window: Gtk.Window) -> bool:
    try:
        parent = window.get_transient_for()
        if parent is None:
            return GLib.SOURCE_REMOVE
        surface = window.get_surface()
        parent_surface = parent.get_surface()
        if surface is None or parent_surface is None:
            return GLib.SOURCE_REMOVE
        px, py = _screen_pos(parent_surface)
        if px is None:
            _center_on_screen_cb(window)
            return GLib.SOURCE_REMOVE
        win_w, win_h = _win_size(window)
        x = px + (parent.get_width() - win_w) // 2
        y = py + (parent.get_height() - win_h) // 2
        _move(surface, x, y)
    except Exception:
        _log.debug("center_on_parent failed", exc_info=True)
    return GLib.SOURCE_REMOVE


# ---------------------------------------------------------------------------
# X11 helpers via python-xlib
# ---------------------------------------------------------------------------


def _xid(surface) -> int | None:
    """Return the X11 Window ID for a GDK surface, or None if not on X11."""
    try:
        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11

        if isinstance(surface, GdkX11.X11Surface):
            return int(surface.get_xid())
    except Exception:
        _log.debug("failed to get X11 window ID", exc_info=True)
    return None


def _screen_pos(surface) -> tuple[int | None, int | None]:
    """Return the absolute screen (x, y) of a surface's top-left corner."""
    xid = _xid(surface)
    if xid is None:
        return None, None
    try:
        from Xlib.display import Display

        d = Display()
        root = d.screen().root
        trans = root.translate_coords(d.create_resource_object("window", xid), 0, 0)
        d.close()
        return trans.x, trans.y
    except Exception:
        _log.debug("failed to get screen position for xid=%s", xid, exc_info=True)
        return None, None


def _move(surface, x: int, y: int) -> None:
    """Move an X11 surface to absolute screen coordinates."""
    xid = _xid(surface)
    if xid is None:
        return
    try:
        from Xlib.display import Display

        d = Display()
        d.create_resource_object("window", xid).configure(x=x, y=y)
        d.sync()
        d.close()
    except Exception:
        _log.debug("failed to move xid=%s to (%s, %s)", xid, x, y, exc_info=True)

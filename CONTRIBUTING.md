# Contributing to repoman

## Getting started

1. Fork the repository and create a feature branch from `main`.
2. Set up your dev environment — see [Running from source](README.md#running-from-source-development) in the README.
3. Make your changes, keeping pull requests focused: one feature or fix per PR.
4. Open a pull request with a clear description of what changed and why.

## Running tests

```bash
python3 -m pytest tests/ -q
```

All 221 tests must pass. Tests are pure (no GTK, no network, no disk writes) and run without any system services.

## Lint and format

```bash
ruff check src/
ruff format src/
```

Both must be clean before submitting.

## Code conventions

See [CLAUDE.md](CLAUDE.md) for the full coding guide, including:

- GTK4 widget selection rules (what to use and what to avoid)
- Import organisation and type hint requirements
- Exception handling rules
- Threading rules (GTK widgets must never be touched from a background thread)
- The polkit helper interface

## What repoman does not accept

- New runtime dependencies beyond the existing set
- Anything that requires a GNOME portal or GNOME-specific services (the target environment is Xfce/Xfwm4)
- `Adw.Dialog` — all windows use `Gtk.Window` for consistent system titlebars
- Window positioning code — placement is left entirely to the window manager

## Reporting bugs

Open an issue at <https://github.com/Tecktron/repoman/issues>. Include your Ubuntu release, repoman version (Help → About Repoman), and steps to reproduce.

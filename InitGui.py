# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD GUI entry point for NeoRibbon."""

from __future__ import annotations

import FreeCAD as App

try:
    from neoribbon.bootstrap import install

    install()
except Exception as exc:  # noqa: BLE001 — surface startup failures in Report View
    App.Console.PrintError(f"NeoRibbon failed to start: {exc}\n")
    raise

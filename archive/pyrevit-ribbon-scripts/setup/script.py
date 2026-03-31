# -*- coding: utf-8 -*-
"""
Setup Model -- Byggstyrning IFC-to-Revit pipeline, Step 1.

Thin pyRevit UI wrapper.  All logic lives in lib/bygg_setup_core.py.
"""

import os.path as op
import sys

from pyrevit import revit, forms

script_dir = op.dirname(__file__)
# scripts/rbp/<task>/script.py -> four levels up to repository root
ext_dir = op.dirname(op.dirname(op.dirname(op.dirname(script_dir))))
lib_path = op.join(ext_dir, "lib")
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

import utils
import bygg_setup_core

__title__ = "Setup Model"
__doc__ = """Performs comprehensive model setup for Revit projects imported from ArchiCAD:

1. Purges IFC opening elements
2. Enables Revit worksharing
3. Creates architectural and structural worksets (names from settings.json)
4. Moves structural elements to the structural workset
5. Rotates all elements from internal origin by the True North angle
6. Sets True North (ProjectPosition angle = 0) and view to Project North
7. Links the coordination config template and acquires coordinates

After running: define Project North via Manage > Position > Rotate Project North."""

doc = revit.doc


def main():
    settings = utils.load_settings()
    result = bygg_setup_core.run_full_setup(doc, settings)

    lines = [
        "Setup completed:",
        "- Purged {} IFC opening elements".format(result.get("openings_deleted", 0)),
        "- {} Worksharing enabled".format(u"\u2713" if result.get("worksharing_enabled") else u"\u2717"),
        "- {} Structural workset created/found".format(u"\u2713" if result.get("struct_ws_created") else u"\u2717"),
        "- {} elements moved to structural workset".format(result.get("structural_moved", 0)),
        "- {} elements rotated by {:.2f}\u00b0".format(
            result.get("elements_rotated", 0),
            settings["default_paths"]["default_true_north_angle"],
        ),
        "- {} True North set".format(u"\u2713" if result.get("true_north_set") else u"\u2717"),
        "- {} View set to Project North".format(u"\u2713" if result.get("project_north_set") else u"\u2717"),
        "- {} Config linked and coordinates acquired".format(u"\u2713" if result.get("config_linked") else u"\u2717"),
        "",
        "Next: define Project North (Manage > Position > Rotate Project North).",
    ]

    if result.get("error"):
        lines.append("\nERROR: " + result["error"])

    forms.alert("\n".join(lines), title="Setup Model")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Batch-convert ALL in-place Generic Models to loadable families (IFC Predefined Type routing)."""

import os.path as op
import sys

from pyrevit import revit, forms

script_dir = op.dirname(__file__)
# Three levels up: pyrevit-convert-inplace -> inplace-convert-kit -> archive -> extension repo root
ext_dir = op.dirname(op.dirname(op.dirname(script_dir)))
lib_path = op.join(ext_dir, "lib")
revit_lib = op.join(lib_path, "revit")
for _p in (revit_lib, lib_path):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import inplace_to_loadable_floor

__title__ = "Convert All\nIn-place \u2192 Loadable"
__doc__ = """Batch-convert every in-place Generic Model in the project to a loadable family.

Routes each element by Type IFC Predefined Type:
- FLOORING / NOTDEFINED -> Floor Family Template
- ROOFING               -> Roofs Family Template
- CEILING               -> Ceiling Family Template

Unmapped predefined types are skipped. Parameters are cached once, geometry is
extracted per element, and cached values are restored on the new loadable instances."""

doc = revit.doc


def main():
    with forms.ProgressBar(title="Converting in-place families...") as pb:
        def on_progress(current, total):
            pb.title = "Converting in-place families ({}/{})".format(current + 1, total)
            pb.update_progress(current, total)

        inplace_to_loadable_floor.batch_convert_all_inplace(
            doc, doc.Application, script_dir,
            progress_callback=on_progress,
        )


if __name__ == "__main__":
    main()

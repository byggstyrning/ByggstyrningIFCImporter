# -*- coding: utf-8 -*-
"""Locate repository root from any RBP script path (no fixed folder depth)."""
import os


def repo_root_from_script(script_path):
    """Return the directory that contains ``lib/`` and ``settings.json``."""
    d = os.path.dirname(os.path.abspath(script_path))
    for _ in range(24):
        if os.path.isdir(os.path.join(d, "lib")) and os.path.isfile(os.path.join(d, "settings.json")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    raise IOError(
        "Could not find repository root (lib/ + settings.json) near: {!r}".format(script_path)
    )

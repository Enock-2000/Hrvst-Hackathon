from __future__ import annotations

import argparse

from detectors.locateanything_backend import LocateAnythingBackend


def create_detector(args: argparse.Namespace) -> LocateAnythingBackend:
    return LocateAnythingBackend.build_from_args(args)

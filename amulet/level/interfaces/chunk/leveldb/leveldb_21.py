# meta interface
from __future__ import annotations

from .leveldb_20 import (
    LevelDB20Interface,
)


class LevelDB21Interface(LevelDB20Interface):
    def __init__(self):
        super().__init__()

        self.features["chunk_version"] = 21


export = LevelDB21Interface

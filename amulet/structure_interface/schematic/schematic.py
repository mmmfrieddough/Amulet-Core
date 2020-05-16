from __future__ import annotations

import os
import numpy
from typing import List, Dict, Tuple, Generator

import amulet_nbt
from amulet.api.selection import SelectionBox
from amulet.api.data_types import PointCoordinates, ChunkCoordinates
from amulet.api.errors import ChunkDoesNotExist

BlockArrayType = numpy.ndarray  # uint16 array
BlockDataArrayType = numpy.ndarray  # uint8 array


class SchematicChunk:
    def __init__(
            self,
            selection: SelectionBox,
            blocks: BlockArrayType,
            data: BlockDataArrayType,
            block_entities: List[amulet_nbt.TAG_Compound],
            entities: List[amulet_nbt.TAG_Compound]
    ):
        self.selection = selection
        self.blocks = blocks
        self.data = data
        self.block_entities = block_entities
        self.entities = entities


class SchematicReader:
    def __init__(self, path: str):
        assert path.endswith(".schematic"), "File selected is not a .schematic file"
        assert os.path.isfile(path), f"There is no schematic file at path {path}"
        schematic = amulet_nbt.load(path)
        materials = schematic.get("Materials", amulet_nbt.TAG_String()).value
        if materials == "Alpha":
            self._platform = "java"
        elif materials == "Pocket":
            self._platform = "bedrock"
        else:
            raise Exception(f"\"{materials}\" is not a supported platform for a schematic file.")
        self._chunks: Dict[ChunkCoordinates, Tuple[SelectionBox, BlockArrayType, BlockDataArrayType, list, list]] = {}
        self._selection = SelectionBox((0, 0, 0), (schematic["Width"], schematic["Height"], schematic["Length"]))
        entities: amulet_nbt.TAG_List = schematic.get("Entities", amulet_nbt.TAG_List())
        block_entities: amulet_nbt.TAG_List = schematic.get("TileEntities", amulet_nbt.TAG_List())
        blocks: numpy.ndarray = schematic["Blocks"].value.astype(numpy.uint16)
        if "AddBlocks" in schematic:
            add_blocks = schematic["AddBlocks"]
            blocks = blocks + (
                    numpy.concatenate([
                        [add_blocks & 0xF],
                        [(add_blocks & 0xF0) >> 4]
                    ]).T.ravel().astype(numpy.uint16) << 8
            )
        blocks = blocks.reshape(self._selection.max)
        data = schematic["Data"].value.reshape(self._selection.max)
        for cx, cz in self._selection.chunk_locations():
            box = SelectionBox(
                (
                    cx*16,
                    0,
                    cz*16
                ),
                (
                    min((cx+1)*16, self._selection.size_x),
                    self._selection.size_y,
                    min((cz+1)*16, self._selection.size_z)
                )
            )
            self._chunks[(cx, cz)] = (box, blocks[box.slice], data[box.slice], [], [])
        for e in block_entities:
            if all(key in e for key in ("x", "y", "z")):
                x, y, z = e["x"].value, e["y"].value, e["z"].value
                if (x, y, z) in self._selection:
                    cx = x >> 4
                    cz = z >> 4
                    self._chunks[(cx, cz)][3].append(e)
        for e in entities:
            if "Pos" in e:
                pos: PointCoordinates = e["Pos"].value
                if pos in self._selection:
                    cx = int(pos[0]) >> 4
                    cz = int(pos[2]) >> 4
                    self._chunks[(cx, cz)][4].append(e)

    def read(self, cx: int, cz: int):
        if (cx, cz) in self._chunks:
            return SchematicChunk(
                *self._chunks[(cx, cz)]
            )
        else:
            raise ChunkDoesNotExist

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def selection(self) -> SelectionBox:
        return self._selection

    @property
    def chunk_coords(self) -> Generator[ChunkCoordinates, None, None]:
        yield from self._chunks.keys()


class SchematicWriter:
    def __init__(
            self,
            path: str,
            platform: str,
            selection: SelectionBox
    ):
        self._path = path
        if platform == "java":
            self._materials = "Alpha"
        elif platform == "bedrock":
            self._materials = "Pocket"
        else:
            raise Exception(f"\"{platform}\" is not a supported platform for a schematic file.")
        self._selection = selection

        self._data = amulet_nbt.NBTFile(
            amulet_nbt.TAG_Compound({
                "TileTicks": amulet_nbt.TAG_List(),
                "Width": amulet_nbt.TAG_Short(selection.size_x),
                "Height": amulet_nbt.TAG_Short(selection.size_y),
                "Length": amulet_nbt.TAG_Short(selection.size_z),
                "Materials": self._materials
            }),
            "Schematic"
        )

        self._entities = []
        self._block_entities = []
        self._blocks = numpy.zeros(selection.shape, dtype=numpy.uint16)  # only 12 bits are actually used at most
        self._block_data = numpy.zeros(selection.shape, dtype=numpy.uint8)  # only 4 bits are used

    def write(self, section: SchematicChunk):
        if section.selection.intersects(self._selection):
            box = section.selection.create_moved_box(-numpy.array(self._selection.min))
            self._blocks[box.slice] = section.blocks
            self._block_data[box.slice] = section.data
            self._block_entities += section.block_entities
            self._entities += section.entities

    def close(self):
        self._data["Entities"] = amulet_nbt.TAG_List(self._entities)
        self._data["TileEntities"] = amulet_nbt.TAG_List(self._block_entities)
        self._data["Data"] = amulet_nbt.TAG_Byte_Array(self._block_data)
        self._data["Blocks"] = amulet_nbt.TAG_Byte_Array((self._blocks & 0xFF).astype(numpy.uint8))
        if numpy.max(self._blocks) > 0xFF:
            add_blocks = (self._blocks & 0xF00) >> 8
            self._data["AddBlocks"] = amulet_nbt.TAG_Byte_Array(
                add_blocks[::2] + (add_blocks[1::2] << 4)
            )
        self._data.save_to(self._path)

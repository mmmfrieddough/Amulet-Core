from __future__ import annotations

from typing import Dict, TYPE_CHECKING

import numpy
from amulet_nbt import (
    TAG_Compound,
    TAG_List,
    TAG_String,
    TAG_Long_Array,
)

from amulet.api.data_types import AnyNDArray
from amulet.api.block import Block
from amulet.api.chunk import Blocks, StatusFormats
from .anvil_0 import Anvil112Interface
from amulet.utils.world_utils import (
    decode_long_array,
    encode_long_array,
)

if TYPE_CHECKING:
    from amulet.api.chunk import Chunk


def properties_to_string(props: dict) -> str:
    """
    Converts a dictionary of blockstate properties to a string

    :param props: The dictionary of blockstate properties
    :return: The string version of the supplied blockstate properties
    """
    result = []
    for key, value in props.items():
        result.append("{}={}".format(key, value))
    return ",".join(result)


class Anvil1444Interface(Anvil112Interface):
    """
    Moved light and terrain populated to Status
    Made blocks paletted
    Added more tick tags
    Added structures tag
    """

    Structures = "structures"

    def __init__(self):
        super().__init__()
        self._set_feature("light_populated", None)
        self._set_feature("terrain_populated", None)
        self._set_feature("status", StatusFormats.Java_13)

        self._set_feature("blocks", "Sections|(BlockStates,Palette)")
        self._set_feature("long_array_format", "compact")

        self._set_feature("liquid_ticks", "list")
        self._set_feature("liquids_to_be_ticked", "16list|list")
        self._set_feature("to_be_ticked", "16list|list")
        self._set_feature("post_processing", "16list|list")
        self._set_feature("structures", "compound")

    @staticmethod
    def minor_is_valid(key: int):
        return 1444 <= key < 1466

    def _decode_level(self, chunk: Chunk, level: TAG_Compound, bounds: Tuple[int, int]):
        super()._decode_level(chunk, level, bounds)
        self._decode_fluid_ticks(chunk, level)
        self._decode_post_processing(chunk, level)
        self._decode_structures(chunk, level)

    def _decode_status(self, chunk: Chunk, compound: TAG_Compound):
        chunk.status = self.get_obj(
            compound, "Status", TAG_String, TAG_String("full")
        ).value

    def _decode_blocks(
        self, chunk: Chunk, chunk_sections: Dict[int, TAG_Compound]
    ) -> AnyNDArray:
        blocks: Dict[int, numpy.ndarray] = {}
        palette = [Block(namespace="minecraft", base_name="air")]

        for cy, section in chunk_sections.items():
            if "Palette" not in section:  # 1.14 makes block_palette/blocks optional.
                continue
            section_palette = self._decode_palette(section.pop("Palette"))
            if self._features["long_array_format"] in ("compact", "1.16"):
                decoded = decode_long_array(
                    section.pop("BlockStates").value,
                    4096,
                    max(4, (len(section_palette) - 1).bit_length()),
                    dense=self._features["long_array_format"] == "compact",
                ).astype(numpy.uint32)
            else:
                raise Exception(
                    "long_array_format", self._features["long_array_format"]
                )
            blocks[cy] = numpy.transpose(
                decoded.reshape((16, 16, 16)) + len(palette), (2, 0, 1)
            )
            palette += section_palette

        np_palette, inverse = numpy.unique(palette, return_inverse=True)
        np_palette: numpy.ndarray
        inverse: numpy.ndarray
        inverse = inverse.astype(numpy.uint32)
        for cy in blocks:
            blocks[cy] = inverse[blocks[cy]]
        chunk.blocks = blocks
        return np_palette

    def _decode_block_ticks(self, chunk: Chunk, compound: TAG_Compound):
        chunk.misc["tile_ticks"] = self.get_obj(compound, "TileTicks", TAG_List)
        chunk.misc["to_be_ticked"] = self.get_obj(compound, "ToBeTicked", TAG_List)

    def _decode_fluid_ticks(self, chunk: Chunk, compound: TAG_Compound):
        chunk.misc["liquid_ticks"] = self.get_obj(compound, "LiquidTicks", TAG_List)
        chunk.misc["liquids_to_be_ticked"] = self.get_obj(
            compound, "LiquidsToBeTicked", TAG_List
        )

    def _decode_post_processing(self, chunk: Chunk, compound: TAG_Compound):
        chunk.misc["post_processing"] = self.get_obj(
            compound, "PostProcessing", TAG_List
        )

    def _decode_structures(self, chunk: Chunk, compound: TAG_Compound):
        chunk.misc["structures"] = self.get_obj(compound, self.Structures, TAG_Compound)

    def _encode_blocks(
        self,
        sections: Dict[int, TAG_Compound],
        blocks: Blocks,
        palette: AnyNDArray,
        cy_min: int,
        cy_max: int,
    ):
        for cy in range(cy_min, cy_max):
            if cy in blocks:
                block_sub_array = numpy.transpose(
                    blocks.get_sub_chunk(cy), (1, 2, 0)
                ).ravel()

                sub_palette_, block_sub_array = numpy.unique(
                    block_sub_array, return_inverse=True
                )
                sub_palette = self._encode_palette(palette[sub_palette_])
                if (
                    len(sub_palette) == 1
                    and sub_palette[0]["Name"].value == "minecraft:air"
                ):
                    continue

                section = sections.setdefault(cy, TAG_Compound())
                if self._features["long_array_format"] == "compact":
                    section["BlockStates"] = TAG_Long_Array(
                        encode_long_array(block_sub_array, min_bits_per_entry=4)
                    )
                elif self._features["long_array_format"] == "1.16":
                    section["BlockStates"] = TAG_Long_Array(
                        encode_long_array(
                            block_sub_array, dense=False, min_bits_per_entry=4
                        )
                    )
                section["Palette"] = sub_palette

    @staticmethod
    def _decode_palette(palette: TAG_List) -> list:
        blockstates = []
        for entry in palette:
            namespace, base_name = entry["Name"].value.split(":", 1)
            properties = entry.get("Properties", TAG_Compound({})).value
            block = Block(
                namespace=namespace, base_name=base_name, properties=properties
            )
            blockstates.append(block)
        return blockstates

    @staticmethod
    def _encode_palette(blockstates: list) -> TAG_List:
        palette = TAG_List()
        for block in blockstates:
            entry = TAG_Compound()
            entry["Name"] = TAG_String(f"{block.namespace}:{block.base_name}")
            entry["Properties"] = TAG_Compound(block.properties)
            palette.append(entry)
        return palette


export = Anvil1444Interface

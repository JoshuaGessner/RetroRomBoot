"""Deterministic image sizing helpers."""

from dataclasses import dataclass

from .errors import RomBootError

MIB = 1024 * 1024


@dataclass(frozen=True)
class ImageLayout:
    boot_mib: int
    root_mib: int
    data_mib: int
    overhead_mib: int = 8

    @property
    def total_mib(self) -> int:
        return self.boot_mib + self.root_mib + self.data_mib + self.overhead_mib

    @property
    def total_bytes(self) -> int:
        return self.total_mib * MIB


def calculate_layout(
    boot_bytes: int,
    root_bytes: int,
    data_bytes: int,
    boot_headroom_mib: int = 8,
    root_headroom_mib: int = 16,
    minimum_data_mib: int = 32,
) -> ImageLayout:
    for name, value in (("boot", boot_bytes), ("root", root_bytes), ("data", data_bytes)):
        if value < 0:
            raise RomBootError("{} size cannot be negative".format(name))
    return ImageLayout(
        boot_mib=_round_mib(boot_bytes) + boot_headroom_mib,
        root_mib=_round_mib(root_bytes) + root_headroom_mib,
        data_mib=max(_round_mib(data_bytes), minimum_data_mib),
    )


def _round_mib(value: int) -> int:
    return (value + MIB - 1) // MIB

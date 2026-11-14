"""Stdlib-only web front-end for RomBoot's Docker build appliance.

This package turns the ``romboot`` command-line builder into a self-hosted web
service: upload one legally obtained ROM in a browser, build a bootable
Raspberry Pi image inside the container, and download the finished artifact.
Flashing is intentionally left to the user's own machine.

Like the terminal wizard, this layer only calls the same ``romboot`` functions
the CLI uses -- nothing is bypassed -- and it depends on the Python standard
library alone, so the whole project stays dependency-free.
"""

__version__ = "0.1.0"

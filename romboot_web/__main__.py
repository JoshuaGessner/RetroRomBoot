"""Start the RomBoot web service: ``python -m romboot_web``."""

from __future__ import annotations

import sys

from .server import make_server
from .settings import Settings


def main(argv=None) -> int:
    settings = Settings.from_env()
    server = make_server(settings)
    where = "http://{}:{}".format(
        "localhost" if settings.host in ("0.0.0.0", "127.0.0.1") else settings.host,
        settings.port,
    )
    print("RomBoot web service listening on {} (bind {})".format(where, settings.host))
    print("  data:      {}".format(settings.data_dir))
    print("  cache:     {}".format(settings.cache_dir))
    print("  buildroot: {}".format(
        settings.buildroot_dir if settings.buildroot_available() else "NOT CONFIGURED"))
    if settings.token:
        print("  auth:      token required")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

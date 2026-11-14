#!/bin/sh
# Make the appliance filesystem shape explicit after Buildroot applies the
# overlay.  The runtime never writes below / except via the mounted /data.
set -eu

: "${TARGET_DIR:?Buildroot target directory is required}"
: "${ROMBOOT_STAGING_ROOT:?RomBoot staging root is required}"

if [ ! -d "$ROMBOOT_STAGING_ROOT" ] || [ -L "$ROMBOOT_STAGING_ROOT" ]; then
	echo "RomBoot: invalid staging root" >&2
	exit 1
fi

set -- "$ROMBOOT_STAGING_ROOT"/rom/*
if [ "$#" -ne 1 ] || [ ! -f "$1" ] || [ -L "$1" ]; then
	echo "RomBoot: staging must contain exactly one regular ROM" >&2
	exit 1
fi
if [ ! -f "$ROMBOOT_STAGING_ROOT/etc/romboot/game.env" ]; then
	echo "RomBoot: staging is missing game.env" >&2
	exit 1
fi

# Residue guard for warm/reused build trees.  When a per-target Buildroot output
# directory is reused across builds (to skip rebuilding the toolchain), the
# target rootfs is not wiped between runs, so a previous game's ROM, BIOS, or
# custom splash could survive.  RomBoot points ROMBOOT_INSTALL_LEDGER at a file
# recording exactly which paths the last build staged; delete those first.  When
# the variable is unset (a clean, one-shot build) this whole block is skipped.
if [ -n "${ROMBOOT_INSTALL_LEDGER:-}" ] && [ -f "$ROMBOOT_INSTALL_LEDGER" ]; then
	while IFS= read -r staged_rel; do
		[ -n "$staged_rel" ] || continue
		rm -f "$TARGET_DIR/$staged_rel"
	done < "$ROMBOOT_INSTALL_LEDGER"
fi
# Enforce the one-ROM invariant even on an incremental rebuild: drop any ROM
# left in the target by a previous build before copying the current staging in.
rm -rf "$TARGET_DIR"/rom
cp -a "$ROMBOOT_STAGING_ROOT"/. "$TARGET_DIR"/

# Record every file this build staged so the next build's residue guard can
# remove exactly this game's content, wherever it landed in the tree.
if [ -n "${ROMBOOT_INSTALL_LEDGER:-}" ]; then
	( cd "$ROMBOOT_STAGING_ROOT" && find . -type f ) | sed 's|^\./||' > "$ROMBOOT_INSTALL_LEDGER"
fi
install -d -m 0755 "$TARGET_DIR/data" "$TARGET_DIR/rom" "$TARGET_DIR/run/romboot"
install -d -m 0755 "$TARGET_DIR/data/saves" "$TARGET_DIR/data/logs"
chmod 0755 "$TARGET_DIR/usr/libexec/romboot-supervisor"
chmod 0755 "$TARGET_DIR/etc/init.d/S01romboot-splash"
chmod 0755 "$TARGET_DIR/etc/init.d/S20romboot-data"
chmod 0755 "$TARGET_DIR/etc/init.d/S90romboot"

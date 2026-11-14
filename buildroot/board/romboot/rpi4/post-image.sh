#!/bin/sh
# Buildroot calls this after rootfs.squashfs and boot artifacts are available.
# The data filesystem is deliberately blank: all persistent state is created at
# first boot by S20romboot-data.
set -eu

BINARIES_DIR="$1"
: "${BR2_EXTERNAL_ROMBOOT_PATH:?RomBoot external tree is required}"
: "${BUILD_DIR:?Buildroot build directory is required}"

data_image="$BINARIES_DIR/data.ext4"
genimage_tmp="$BUILD_DIR/genimage.tmp"

rm -f "$data_image"
truncate -s 32M "$data_image"
mkfs.ext4 -q -F -L ROMBOOT-DATA -m 0 "$data_image"

# rpi-firmware installs the boot files under rpi-firmware/; genimage's boot.vfat
# expects them at the images-dir root. Stage the exact names it references.
for boot_file in config.txt cmdline.txt fixup4cd.dat start4cd.elf; do
	cp -f "$BINARIES_DIR/rpi-firmware/$boot_file" "$BINARIES_DIR/$boot_file"
done

rm -rf "$genimage_tmp"
mkdir -p "$genimage_tmp"
genimage \
	--rootpath "${TARGET_DIR:?}" \
	--tmppath "$genimage_tmp" \
	--inputpath "$BINARIES_DIR" \
	--outputpath "$BINARIES_DIR" \
	--config "$BR2_EXTERNAL_ROMBOOT_PATH/board/romboot/rpi4/genimage.cfg"

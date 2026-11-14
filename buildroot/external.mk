# Runtime files are installed through the rootfs overlay selected by each
# target defconfig.  Keep this file so Buildroot recognizes the external tree.

include $(BR2_EXTERNAL_ROMBOOT_PATH)/package/romboot-retroarch/romboot-retroarch.mk
include $(BR2_EXTERNAL_ROMBOOT_PATH)/package/romboot-libretro-fceumm/romboot-libretro-fceumm.mk
include $(BR2_EXTERNAL_ROMBOOT_PATH)/package/romboot-joypad-autoconfig/romboot-joypad-autoconfig.mk
include $(BR2_EXTERNAL_ROMBOOT_PATH)/package/romboot-libretro-snes9x2010/romboot-libretro-snes9x2010.mk
include $(BR2_EXTERNAL_ROMBOOT_PATH)/package/romboot-libretro-genesis-plus-gx/romboot-libretro-genesis-plus-gx.mk
include $(BR2_EXTERNAL_ROMBOOT_PATH)/package/romboot-libretro-gambatte/romboot-libretro-gambatte.mk
include $(BR2_EXTERNAL_ROMBOOT_PATH)/package/romboot-libretro-mgba/romboot-libretro-mgba.mk
include $(BR2_EXTERNAL_ROMBOOT_PATH)/package/romboot-libretro-beetle-pce-fast/romboot-libretro-beetle-pce-fast.mk

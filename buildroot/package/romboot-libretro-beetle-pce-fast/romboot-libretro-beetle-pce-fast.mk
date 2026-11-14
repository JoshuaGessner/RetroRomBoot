################################################################################
# RomBoot-pinned Beetle PCE Fast libretro core (PC Engine / TurboGrafx-16)
################################################################################

ROMBOOT_LIBRETRO_BEETLE_PCE_FAST_VERSION = 9e6510023545007e235117753329946cbc5f311a
ROMBOOT_LIBRETRO_BEETLE_PCE_FAST_SITE = https://github.com/libretro/beetle-pce-fast-libretro.git
ROMBOOT_LIBRETRO_BEETLE_PCE_FAST_SITE_METHOD = git
ROMBOOT_LIBRETRO_BEETLE_PCE_FAST_LICENSE = GPL-2.0

define ROMBOOT_LIBRETRO_BEETLE_PCE_FAST_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(TARGET_CONFIGURE_OPTS) $(MAKE) -C $(@D) \
		platform=unix
endef

define ROMBOOT_LIBRETRO_BEETLE_PCE_FAST_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/mednafen_pce_fast_libretro.so \
		$(TARGET_DIR)/usr/lib/libretro/mednafen_pce_fast_libretro.so
endef

$(eval $(generic-package))

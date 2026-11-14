################################################################################
# RomBoot-pinned Snes9x 2010 libretro core (SNES)
################################################################################

ROMBOOT_LIBRETRO_SNES9X2010_VERSION = da064275845dfa57e14eb0e5b5c7ddcc117e9f06
ROMBOOT_LIBRETRO_SNES9X2010_SITE = https://github.com/libretro/snes9x2010.git
ROMBOOT_LIBRETRO_SNES9X2010_SITE_METHOD = git
ROMBOOT_LIBRETRO_SNES9X2010_LICENSE = Snes9x-non-commercial

define ROMBOOT_LIBRETRO_SNES9X2010_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(TARGET_CONFIGURE_OPTS) $(MAKE) -C $(@D) \
		-f Makefile.libretro platform=unix
endef

define ROMBOOT_LIBRETRO_SNES9X2010_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/snes9x2010_libretro.so \
		$(TARGET_DIR)/usr/lib/libretro/snes9x2010_libretro.so
endef

$(eval $(generic-package))

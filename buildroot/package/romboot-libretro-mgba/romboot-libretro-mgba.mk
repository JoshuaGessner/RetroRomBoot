################################################################################
# RomBoot-pinned mGBA libretro core (Game Boy Advance)
################################################################################

ROMBOOT_LIBRETRO_MGBA_VERSION = 6dce57eef127dc4cc292644f38196e0e7c58590c
ROMBOOT_LIBRETRO_MGBA_SITE = https://github.com/libretro/mgba.git
ROMBOOT_LIBRETRO_MGBA_SITE_METHOD = git
ROMBOOT_LIBRETRO_MGBA_LICENSE = MPL-2.0

define ROMBOOT_LIBRETRO_MGBA_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(TARGET_CONFIGURE_OPTS) $(MAKE) -C $(@D) \
		-f Makefile.libretro platform=unix
endef

define ROMBOOT_LIBRETRO_MGBA_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/mgba_libretro.so \
		$(TARGET_DIR)/usr/lib/libretro/mgba_libretro.so
endef

$(eval $(generic-package))

################################################################################
# RomBoot-pinned Genesis Plus GX libretro core (Genesis/MD, SMS, GG, SG-1000)
################################################################################

ROMBOOT_LIBRETRO_GENESIS_PLUS_GX_VERSION = fa4dca561e08d5be9077419f7b255e1da213ed21
ROMBOOT_LIBRETRO_GENESIS_PLUS_GX_SITE = https://github.com/libretro/Genesis-Plus-GX.git
ROMBOOT_LIBRETRO_GENESIS_PLUS_GX_SITE_METHOD = git
ROMBOOT_LIBRETRO_GENESIS_PLUS_GX_LICENSE = Genesis-Plus-GX-non-commercial

define ROMBOOT_LIBRETRO_GENESIS_PLUS_GX_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(TARGET_CONFIGURE_OPTS) $(MAKE) -C $(@D) \
		-f Makefile.libretro platform=unix
endef

define ROMBOOT_LIBRETRO_GENESIS_PLUS_GX_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/genesis_plus_gx_libretro.so \
		$(TARGET_DIR)/usr/lib/libretro/genesis_plus_gx_libretro.so
endef

$(eval $(generic-package))

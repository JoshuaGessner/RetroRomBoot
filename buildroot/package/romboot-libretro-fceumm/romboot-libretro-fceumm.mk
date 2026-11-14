################################################################################
# RomBoot-pinned FCEUmm libretro core
################################################################################

ROMBOOT_LIBRETRO_FCEUMM_VERSION = 38440e42415e1db959ea030a121f48736d96adc4
ROMBOOT_LIBRETRO_FCEUMM_SITE = https://github.com/libretro/libretro-fceumm.git
ROMBOOT_LIBRETRO_FCEUMM_SITE_METHOD = git
ROMBOOT_LIBRETRO_FCEUMM_LICENSE = GPL-2.0

define ROMBOOT_LIBRETRO_FCEUMM_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(TARGET_CONFIGURE_OPTS) $(MAKE) -C $(@D) \
		platform=unix
endef

define ROMBOOT_LIBRETRO_FCEUMM_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/fceumm_libretro.so \
		$(TARGET_DIR)/usr/lib/libretro/fceumm_libretro.so
endef

$(eval $(generic-package))

################################################################################
# RomBoot-pinned Gambatte libretro core (Game Boy / Game Boy Color)
################################################################################

ROMBOOT_LIBRETRO_GAMBATTE_VERSION = 9b3b5e3cc18ec92f460d37dd551eaf90c55bfcea
ROMBOOT_LIBRETRO_GAMBATTE_SITE = https://github.com/libretro/gambatte-libretro.git
ROMBOOT_LIBRETRO_GAMBATTE_SITE_METHOD = git
ROMBOOT_LIBRETRO_GAMBATTE_LICENSE = GPL-2.0

define ROMBOOT_LIBRETRO_GAMBATTE_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(TARGET_CONFIGURE_OPTS) $(MAKE) -C $(@D) \
		-f Makefile.libretro platform=unix
endef

define ROMBOOT_LIBRETRO_GAMBATTE_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/gambatte_libretro.so \
		$(TARGET_DIR)/usr/lib/libretro/gambatte_libretro.so
endef

$(eval $(generic-package))

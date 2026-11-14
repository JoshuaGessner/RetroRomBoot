################################################################################
# RomBoot-pinned RetroArch
################################################################################

ROMBOOT_RETROARCH_VERSION = baee906ef35b99283f9a1a060a2ce5ac86159b63
ROMBOOT_RETROARCH_SITE = https://github.com/libretro/RetroArch.git
ROMBOOT_RETROARCH_SITE_METHOD = git
ROMBOOT_RETROARCH_LICENSE = GPL-3.0
ROMBOOT_RETROARCH_LICENSE_FILES = COPYING
ROMBOOT_RETROARCH_DEPENDENCIES = host-pkgconf alsa-lib libdrm mesa3d eudev zlib

ROMBOOT_RETROARCH_CONF_OPTS = \
	--prefix=/usr \
	--sysconfdir=/etc \
	--host=$(GNU_TARGET_NAME) \
	--enable-kms \
	--enable-egl \
	--enable-opengles \
	--enable-alsa \
	--enable-udev \
	--disable-x11 \
	--disable-menu \
	--disable-wayland \
	--disable-sdl \
	--disable-sdl2 \
	--disable-vulkan \
	--disable-ffmpeg \
	--disable-networking \
	--disable-netplaydiscovery \
	--disable-online_updater \
	--disable-update_cores \
	--disable-update_core_info \
	--disable-update_assets \
	--disable-cheevos \
	--disable-v4l2 \
	--disable-pulse \
	--disable-jack \
	--disable-oss

define ROMBOOT_RETROARCH_CONFIGURE_CMDS
	(cd $(@D) && $(TARGET_CONFIGURE_OPTS) PKG_CONF_PATH=$(HOST_DIR)/bin/pkg-config ./configure $(ROMBOOT_RETROARCH_CONF_OPTS))
endef

define ROMBOOT_RETROARCH_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(MAKE) -C $(@D)
endef

define ROMBOOT_RETROARCH_INSTALL_TARGET_CMDS
	$(TARGET_MAKE_ENV) $(MAKE) -C $(@D) DESTDIR=$(TARGET_DIR) install
endef

$(eval $(generic-package))

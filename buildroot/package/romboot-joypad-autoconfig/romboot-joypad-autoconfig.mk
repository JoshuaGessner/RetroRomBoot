################################################################################
# RomBoot-pinned RetroArch joypad autoconfiguration profiles (udev)
################################################################################

ROMBOOT_JOYPAD_AUTOCONFIG_VERSION = 7a44e4aa65f1c5380867e9088d8764d585341aa4
ROMBOOT_JOYPAD_AUTOCONFIG_SITE = https://github.com/libretro/retroarch-joypad-autoconfig.git
ROMBOOT_JOYPAD_AUTOCONFIG_SITE_METHOD = git
ROMBOOT_JOYPAD_AUTOCONFIG_LICENSE = MIT

# Data only (no build): install the udev-driver joypad profiles so RetroArch can
# auto-map any USB controller with a known vendor/product id on connect.
define ROMBOOT_JOYPAD_AUTOCONFIG_INSTALL_TARGET_CMDS
	$(INSTALL) -d $(TARGET_DIR)/usr/share/libretro/autoconfig
	cp -rf $(@D)/udev $(TARGET_DIR)/usr/share/libretro/autoconfig/
	# Two bundled profiles share VID 2079 / PID 58369 (a DragonRise-style generic
	# pad). Qnix_SNES_Replica.cfg maps that pad's axes to an analog STICK and
	# leaves the D-pad unbound, and it can win autoconfig selection over the
	# correct USB_gamepad.cfg (which maps those axes to the D-pad) - which kills
	# D-pad movement. Drop the broken duplicate so the D-pad is deterministic.
	rm -f $(TARGET_DIR)/usr/share/libretro/autoconfig/udev/Qnix_SNES_Replica.cfg
endef

$(eval $(generic-package))

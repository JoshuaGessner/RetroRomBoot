.PHONY: test check

test:
	python3 -m unittest discover -s tests -v

check: test
	python3 -m compileall -q romboot romboot_web tests
	for file in platforms/*.json; do cmp "$$file" "romboot/data/$$file"; done
	cmp dependencies.lock.json romboot/data/dependencies.lock.json
	sh -n buildroot/board/romboot/common/post-build.sh
	sh -n buildroot/board/romboot/rpi4/post-image.sh
	sh -n buildroot/board/romboot/rpizero2w/post-image.sh
	sh -n buildroot/board/romboot/common/rootfs-overlay/etc/init.d/S01romboot-splash
	sh -n buildroot/board/romboot/common/rootfs-overlay/etc/init.d/S20romboot-data
	sh -n buildroot/board/romboot/common/rootfs-overlay/etc/init.d/S90romboot
	sh -n buildroot/board/romboot/common/rootfs-overlay/usr/libexec/romboot-supervisor

# Safe flashing

Writing an image overwrites a storage device. Selecting the wrong device can destroy data, including a host operating system. Build images first, verify them, then flash only a removable target you have identified by model and capacity.

```sh
romboot verify game.img.zst
romboot flash game.img.zst /dev/DEVICE
```

`romboot flash` is designed to be the only privileged step. Before it writes, it must:

1. resolve the supplied device to a canonical path;
2. show the model, capacity, and any mounted volumes;
3. reject a device that is too small or appears to be the active system disk;
4. unmount only the selected target’s mounted partitions safely;
5. require an explicit confirmation (except an intentionally restricted CI force option);
6. write the exact verified image; and
7. perform a post-write checksum or representative verification sample.

It must never choose a disk merely because it is newest, use an ambiguous mount path, or infer approval from `--output`. Disconnect other removable drives when practical. If the shown model, capacity, or mounts are surprising, stop rather than confirm.

After a verified write completes, eject the card cleanly, insert it into the configured Raspberry Pi, connect display and input, and power on. A successful write proves only the card contains the image; it does not prove an emulator, display, audio, or controller will function on a particular board.

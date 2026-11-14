# Adding a platform or Raspberry Pi target

This guide defines the intended contribution boundary. Do not claim a new system works until its image and physical behavior are tested.

## Add a platform

Platform knowledge belongs in a declarative registry, not scattered through CLI conditionals. A platform entry must provide:

- stable ID, display name, aliases, and accepted content extensions;
- archive and multi-file-disc policy;
- compatible emulator/core identifiers plus a justified default;
- required/optional BIOS specifications, accepted names, destination paths, and documented digests when authoritative;
- video, audio, aspect-ratio, scaling, region, and controller defaults;
- save behavior, supported target IDs, and known performance limitations; and
- license/redistribution constraints.

Then add the bounded adapter/package configuration needed by the chosen core, validation fixtures that contain no copyrighted ROM or BIOS data, and tests for detection, validation, arguments, staging, and manifest output. Confirm that exactly one selected game and only required BIOS files reach the image. Update the matrix and legal documentation.

For BIOS-dependent platforms, tests can validate the missing/mismatch paths with synthetic metadata; do not add a proprietary BIOS fixture. Never auto-download a missing BIOS.

## Add a Raspberry Pi target

A target profile specifies a board identifier, architecture, pinned firmware/kernel configuration, boot files, display/input/audio expectations, partition/image layout, emulator compatibility, and known constraints. It must also set realistic minimum storage requirements.

Add structural tests for its image and a physical hardware checklist covering cold boot, splash, hidden boot text, controller, HDMI display, audio, game launch, saves, shutdown, crash handling, repeated boots, and power-loss recovery. Test every emulator/core combination separately; one booting NES image does not validate a target for demanding platforms.

## Documentation and review

Every addition updates [the support matrix](support-matrix.md), license records, reproducibility inputs, and hardware results. Include exact board revision, display path, controller, core/version, ROM type, and observed limitations in test evidence. Keep configurations explicit and reject unknown fields to avoid accidental unsupported combinations.

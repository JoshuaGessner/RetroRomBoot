# Controllers, saves, and safe shutdown

## Input

Release images work without a desktop environment. The MVP includes RetroArch's udev input driver and its built-in default mappings; exact USB gamepad and wired-keyboard behavior remains a physical-hardware test item. No downloadable controller profiles or runtime remapping UI are enabled.

The intended control model keeps these actions distinct:

| Action | Purpose | Safety expectation |
| --- | --- | --- |
| Emulator menu | Disabled in the MVP release build | Prevents browsing/loading another game or changing appliance configuration |
| Reset game | Restart the current game | Requires an intentional configured chord |
| Quit emulator | End gameplay | Follows the runtime exit policy; does not silently leave a login prompt |
| Shut down system | Flushes persistent data and powers down cleanly | Uses a deliberate, configurable chord or optional hardware button |
| Force power-off | Physical emergency only | May lose data; never the normal software path |

The default shutdown chord must be difficult to trigger accidentally. It is configured per profile and should be documented in an image’s effective configuration. A controlled shutdown is always preferred to removing power during writes.

## Save modes

Select a mode explicitly at build time:

| Mode | Writable storage | What survives reboot |
| --- | --- | --- |
| `persistent` | Small data partition | Emulator-supported saves, memory-card files, SRAM, and save states that the configured emulator writes there |
| `ephemeral` | `tmpfs` only | Nothing; all runtime saves disappear at shutdown or power loss |
| `disabled` | No game save destination | No emulator game saves should be written; unsupported cores must fail configuration rather than silently changing behavior |

Configuration changes are not a user-facing feature of a release image. Bounded diagnostic data is separate from saves and should not grow without limit. The exact emulator-specific save-state and memory-card behavior must appear in the manifest/runtime documentation once a core is integrated.

## Runtime behavior

The supervisor creates only required runtime directories, displays the splash, starts the configured emulator with an explicit ROM path, and captures bounded diagnostics. It handles shutdown signals and stops restart loops. Following an emulator failure or exit, the configured policy is one of:

1. safe shutdown;
2. a limited number of restarts; or
3. a generic error screen waiting for safe shutdown.

Release images must never drop into an unrestricted shell. Developer diagnostics, including a serial console if added, are opt-in and visibly different from the release configuration.

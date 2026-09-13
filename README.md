# Vaillant Modbus Gateway

Home Assistant custom integration for the **Vaillant Gateway eBUS/Modbus SV2**.
It exposes gateway diagnostics, system data, domestic hot water, up to three
heating circuits (circuits 2 and 3 opt-in), heat-pump parameters, up to two
heat generators, errors, and energy counters. Version: **0.1.0**; domain: `vaillant_modbus`.

The SV2 gateway translates data between a Vaillant eBUS heating system and
Modbus. This integration does not open another TCP, UDP, or serial connection.
It borrows the connection managed by Home Assistant. It prefers Home
Assistant's shared `modbus_connection` per-unit API and also supports the
existing Home Assistant `modbus` hub during the Core API transition.

## Supported systems

The supplied Vaillant Modbus manual V1.20 lists these supported products:

- aroTHERM split
- aroTHERM plus
- ecoTEC plus
- ecoTEC exclusive
- ecoCOMPACT
- ecoVIT exclusive / plus
- ecoCRAFT exclusive
- multiMATIC 700 (VRC 700)
- sensoCOMFORT (VRC 720)
- VR71 heating-circuit extension
- VR32 eBUS coupler

Actual registers and entities depend on the installed hydraulic system,
controller firmware, VR71/VR32 modules, and heat generator. The integration
detects optional components conservatively. Missing optional register blocks do
not take down the gateway.

## Prerequisites

Configure the Modbus transport in Home Assistant first. With the newer shared
connection integration, add a `modbus_connection` in **Settings > Devices &
services**. On Home Assistant versions that still use the YAML Modbus hub:

```yaml
modbus:
  - name: vaillant_gateway
    type: tcp
    host: 192.0.2.10
    port: 502
```

Serial and RTU-over-TCP connections are supported as long as Home Assistant
owns them. Do not configure the same physical link twice.

## Local installation

Copy this repository's directory:

```text
custom_components/vaillant_modbus/
```

to:

```text
/config/custom_components/vaillant_modbus/
```

Restart Home Assistant, then clear the browser cache if the integration does
not appear immediately.

## Installation through HACS

1. Open HACS.
2. Add this GitHub repository as a **Custom repository** of type
   **Integration**.
3. Search for **Vaillant Modbus Gateway** and install it.
4. Restart Home Assistant.

HACS is used only for installation and updates; the integration contains no
HACS-specific runtime logic.

## Setup

1. Configure and start the Modbus connection in Home Assistant.
2. Add **Vaillant Modbus Gateway** under **Settings > Devices & services**.
3. Select the existing Modbus connection.
4. Enter the gateway Unit ID (`1` by default; valid range `1`–`247`).
5. Choose the access mode. **Read only** is the default for new installations
   and never sends a write to the heating system; **Read and write** allows
   changes from Home Assistant.
6. Enable heating circuit 2 and heating circuit 3 if the system has them. Both
   are **off by default** and can be switched on independently of each other.

The config flow reads holding registers `3000`–`3005`. Setup is rejected if the
gateway does not return exactly six valid 16-bit words. A connection/Unit-ID
pair can be configured only once.

The polling interval, the access mode, and both optional heating circuits can
be changed at any time under **Configure**, without removing the integration.
The interval accepts 5, 10, 30, or 60 seconds and defaults to 10 seconds.
Individual requests are spaced by at least one second and never read more than
16 registers.

## Optional heating circuits

Heating circuit 1 is always present. Heating circuits 2 and 3 are opt-in and
are controlled by two independent switches in the setup dialog and under
**Configure**:

- A disabled circuit is never polled, so it costs no bus traffic, and it
  produces no entities and no device.
- Enabling a circuit is allowed even when the gateway does not report a VR71
  extension. The blocks are optional, so a system that does not answer them
  degrades to unavailable entities instead of failing the whole integration.
- Disabling a circuit removes its entities and its device from the registries,
  so nothing is left behind as permanently unavailable.

The choice comes from the configuration alone and never from a register read.
An eBUS or controller outage therefore cannot add or remove heating-circuit
entities. Changes take effect after the automatic reload that follows saving
the options.

## Implemented registers

| Area | Registers | Entities / notes |
| --- | ---: | --- |
| Domestic hot water | 1–8 | Target/actual temperature, charging settings, pump |
| Heating circuit 1 | 100–110 | Temperatures, curve, mode, pump, special mode |
| Heating circuit 2 | 150–160 | As circuit 1; off unless enabled in the options |
| Heating circuit 3 | 200–210 | As circuit 1; off unless enabled in the options |
| Heat pump | 500–507 | Signed temperatures and translated enum parameters |
| System | 550–554 | Outdoor temperature, controller, mode, hydraulic data |
| System energy | 560–567 | 32-bit big-endian counters in kWh |
| Heat generator 1 | 1000–1012 | Errors, temperatures, pressure, pumps, flame |
| Heat generator 1 energy | 1050–1065 | 64-bit big-endian counters in Wh |
| Heat generator 2 | 1200–1212 | Optional VR32 heat generator |
| Heat generator 2 energy | 1250–1265 | 64-bit big-endian counters in Wh |
| Gateway | 3000–3005 | Version, eBUS/controller/VR71 status |

Reserved registers, including register `0`, are never read or written.
Holding registers use function `0x03`; single writable parameters use function
`0x06`.

## Writing and safety

The access mode decides whether the integration may write at all. In
`read_only` mode every write is rejected centrally in the coordinator, before
the value is even encoded, so no write ever reaches the bus. In `read_write`
mode the integration behaves as described below.

**The set of entities is identical in both modes.** Read-only mode hides
nothing: all numbers, selects, and switches remain and keep showing their
current value, so dashboards, automations, history, and entity IDs survive a
mode change unchanged. Existing installations that are updated to this version
keep write access; only newly added entries default to read-only.

Writable entities are generated only for parameters explicitly marked `RD/WR`
in manual V1.20. Values are validated against documented minimum, maximum, and
step constraints before encoding. Signed values use two's complement and
scaled values are converted back exactly. Multi-register values and all
read-only definitions are rejected by the central write path. After a
successful write, the coordinator refreshes the affected state.

Because this controls heating equipment, test changes carefully and retain the
installer's original configuration.

## Diagnostics

Use **Download diagnostics** on the integration entry. The report includes
gateway/controller versions, status flags, capabilities, the active access
mode, the enabled heating circuits, last successful poll, and failed optional
blocks. Connection identifiers and all transport/network
details are redacted.

## Debug logging

```yaml
logger:
  default: warning
  logs:
    custom_components.vaillant_modbus: debug
```

Restart or reload logging, reproduce the issue, and download diagnostics. Do
not post a complete Home Assistant configuration publicly.

## Known limitations

- Time programs in registers `600`–`613` are intentionally not supported in
  0.1.0. They require a transactional day/system/trigger/busy/queue workflow;
  exposing them as independent number entities would be unsafe.
- Heating circuits 2 and 3 are never auto-enabled. A system with a VR71
  extension needs both switches turned on once, in the setup dialog or under
  **Configure**.
- There is no explicit VR32 presence register. Heat generator 2 is exposed only
  after successful reads with meaningful data.
- Heat-pump presence is inferred conservatively from valid, non-zero parameter
  data.
- Optional hardware added while Home Assistant is running may require an
  integration reload before its entities are created.
- In read-only mode, `number`, `select`, and `switch` entities still look
  operable in the user interface. Operating one produces an error message and
  the value jumps back to the last polled state. Automations that write in this
  mode fail loudly rather than being silently ineffective; switching back to
  read and write is a single change under **Configure**.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for test, lint, local-link, and validation
commands.

## Source

Register semantics are implemented from
`01_Modbus_Handbuch_V120.pdf`, Vaillant Deutschland GmbH & Co. KG,
Gateway eBUS/Modbus SV2, version 1.20.0 (29 September 2023).

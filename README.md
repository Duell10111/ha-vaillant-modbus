# Vaillant Modbus Gateway

Home Assistant custom integration for the **Vaillant Gateway eBUS/Modbus SV2**.
It exposes gateway diagnostics, system data, domestic hot water, up to three
heating circuits, heat-pump parameters, up to two heat generators, errors, and
energy counters. Version: **0.1.0**; domain: `vaillant_modbus`.

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

The config flow reads holding registers `3000`–`3005`. Setup is rejected if the
gateway does not return exactly six valid 16-bit words. A connection/Unit-ID
pair can be configured only once.

The polling interval can be changed under **Configure** to 5, 10, 30, or 60
seconds. The default is 10 seconds. Individual requests are spaced by at least
one second and never read more than 16 registers.

## Implemented registers

| Area | Registers | Entities / notes |
| --- | ---: | --- |
| Domestic hot water | 1–8 | Target/actual temperature, charging settings, pump |
| Heating circuit 1 | 100–110 | Temperatures, curve, mode, pump, special mode |
| Heating circuit 2 | 150–160 | As circuit 1; only with detected VR71 |
| Heating circuit 3 | 200–210 | As circuit 1; only with detected VR71 |
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
gateway/controller versions, status flags, capabilities, last successful poll,
and failed optional blocks. Connection identifiers and all transport/network
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
- There is no explicit VR32 presence register. Heat generator 2 is exposed only
  after successful reads with meaningful data.
- Heat-pump presence is inferred conservatively from valid, non-zero parameter
  data.
- Optional hardware added while Home Assistant is running may require an
  integration reload before its entities are created.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for test, lint, local-link, and validation
commands.

## Source

Register semantics are implemented from
`01_Modbus_Handbuch_V120.pdf`, Vaillant Deutschland GmbH & Co. KG,
Gateway eBUS/Modbus SV2, version 1.20.0 (29 September 2023).

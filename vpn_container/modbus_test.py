#!/usr/bin/env python3
"""Diagnosetest fuer das Vaillant Gateway eBUS/Modbus SV2.

Das Skript liest die im Modbus-Handbuch beschriebenen Datenbereiche in
Bloecken von hoechstens 16 Registern. Neben dem Rohwert werden fuer jedes
Register eine Bezeichnung und - soweit die Bedeutung bekannt ist - eine
menschlich lesbare Interpretation ausgegeben.
"""

import argparse
import sys
import time
from datetime import datetime

try:
    from pymodbus.client import ModbusTcpClient
except ImportError:
    ModbusTcpClient = None


# Das Handbuch verwendet 1-basierte Registernummern. read_block() rechnet sie
# fuer pymodbus in 0-basierte Adressen um.
REGISTER_BEREICHE = [
    (1, 8, "Warmwasser"),
    (100, 110, "HK1"),
    (150, 160, "HK2"),
    (200, 210, "HK3"),
    (500, 507, "Waermepumpe"),
    (550, 554, "System"),
    (560, 567, "Energie"),
    (3000, 3005, "Gateway"),
]


# Typen steuern ausschliesslich die Darstellung; gelesen werden immer die
# unveraenderten 16-Bit-Rohwerte. Bei nicht eindeutig dokumentierten Feldern
# wird absichtlich nur der Rohwert ausgegeben.
REGISTER_INFO = {
    # Warmwasser
    1: ("WW Soll-Temperatur", "temperature"),
    2: ("WW Ist-Temperatur", "temperature"),
    3: ("Warmwasser Register 3", "raw"),
    4: ("Warmwasser Register 4", "raw"),
    5: ("Warmwasser Register 5", "raw"),
    6: ("Warmwasser Register 6", "raw"),
    7: ("Warmwasser Register 7", "raw"),
    8: ("Warmwasser Register 8", "raw"),

    # Heizkreis 1
    100: ("HK1 Soll-Temperatur Vorlauf", "temperature"),
    101: ("HK1 Ist-Temperatur Vorlauf", "temperature"),
    102: ("HK1 Heizkurve", "number"),
    103: ("HK1 Register 103", "raw"),
    104: ("HK1 Register 104", "raw"),
    105: ("HK1 Betriebsart", "heating_mode"),
    106: ("HK1 Register 106", "raw"),
    107: ("HK1 Register 107", "raw"),
    108: ("HK1 Pumpe", "pump"),
    109: ("HK1 Register 109", "raw"),
    110: ("HK1 Register 110", "raw"),

    # Heizkreis 2
    150: ("HK2 Soll-Temperatur Vorlauf", "temperature"),
    151: ("HK2 Ist-Temperatur Vorlauf", "temperature"),
    152: ("HK2 Register 152", "raw"),
    153: ("HK2 Register 153", "raw"),
    154: ("HK2 Register 154", "raw"),
    155: ("HK2 Betriebsart", "heating_mode"),
    156: ("HK2 Register 156", "raw"),
    157: ("HK2 Register 157", "raw"),
    158: ("HK2 Pumpe", "pump"),
    159: ("HK2 Register 159", "raw"),
    160: ("HK2 Register 160", "raw"),

    # Heizkreis 3
    200: ("HK3 Soll-Temperatur Vorlauf", "temperature"),
    201: ("HK3 Ist-Temperatur Vorlauf", "temperature"),
    202: ("HK3 Register 202", "raw"),
    203: ("HK3 Register 203", "raw"),
    204: ("HK3 Register 204", "raw"),
    205: ("HK3 Betriebsart", "heating_mode"),
    206: ("HK3 Register 206", "raw"),
    207: ("HK3 Register 207", "raw"),
    208: ("HK3 Pumpe", "pump"),
    209: ("HK3 Register 209", "raw"),
    210: ("HK3 Register 210", "raw"),

    # Waermepumpe
    500: ("WP Temperatur Register 500", "temperature"),
    501: ("WP Temperatur Register 501", "temperature"),
    502: ("WP Temperatur Register 502", "temperature"),
    503: ("Waermepumpe Register 503", "raw"),
    504: ("WP Temperatur Register 504", "temperature"),
    505: ("Waermepumpe Register 505", "raw"),
    506: ("WP Temperatur Register 506", "temperature"),
    507: ("Waermepumpe Register 507", "raw"),

    # System
    550: ("System Aussentemperatur", "temperature"),
    551: ("Reglerversion", "controller"),
    552: ("System Sonderbetriebsart", "special_mode"),
    553: ("VRC Hydraulikplan", "number"),
    554: ("VR71 Konfiguration", "number"),

    # Energiezaehler (Einheit laut Handbuch: kWh)
    560: ("Energiezaehler 1", "energy"),
    561: ("Energiezaehler 2", "energy"),
    562: ("Energiezaehler 3", "energy"),
    563: ("Energiezaehler 4", "energy"),
    564: ("Energiezaehler 5", "energy"),
    565: ("Energiezaehler 6", "energy"),
    566: ("Energiezaehler 7", "energy"),
    567: ("Energiezaehler 8", "energy"),

    # Gateway-Diagnose
    3000: ("Gateway Version Major", "version"),
    3001: ("Gateway Version Minor", "version"),
    3002: ("Gateway Version Iteration", "version"),
    3003: ("eBUS Kommunikation aktiv", "ebus_active"),
    3004: ("Systemregler aktiv", "controller_active"),
    3005: ("VR71 vorhanden", "vr71_available"),
}


SPECIAL_MODES = {
    0: "Keine Sonderbetriebsart",
    1: "Stosslueften",
    2: "Manuelles Kuehlen",
    3: "Party",
    4: "QuickVeto",
    5: "Urlaubstag",
    6: "Feiertag",
    7: "Tage ausser Haus",
    8: "Feiertage",
    9: "Einmalige Speicherladung",
    10: "System AUS (Frostschutz aktiv)",
}

HEATING_MODES = {
    0: "Aus / Frostschutz",
    1: "Auto",
    2: "Tag / Manuell",
    3: "Nacht",
}

DHW_MODES = {
    0: "Aus",
    1: "Auto",
    2: "Ein / Tagbetrieb",
}


def signed_16(value):
    """Interpretiert einen Modbus-U16-Rohwert als vorzeichenbehaftetes S16."""
    return value - 0x10000 if value & 0x8000 else value


def register_name(register, area):
    """Liefert auch fuer Reserve-/unbekannte Register eine klare Benennung."""
    return REGISTER_INFO.get(register, (f"{area} Register {register}", "raw"))[0]


def interpret_register(register, value, values):
    """Erzeugt eine menschenlesbare Interpretation eines Rohwertes."""
    info = REGISTER_INFO.get(register)
    value_type = info[1] if info else "raw"

    if value_type == "temperature":
        return f"{signed_16(value) / 10:.1f} °C"

    if value_type == "controller":
        controllers = {700: "VRC700", 720: "VRC720"}
        return controllers.get(value, f"Unbekannter Reglercode ({value})")

    if value_type == "version":
        if all(reg in values for reg in (3000, 3001, 3002)):
            return (
                "Gateway-Version "
                f"{values[3000]}.{values[3001]}.{values[3002]}"
            )
        return "Versionsbestandteil"

    if value_type == "pump":
        return {0: "AUS", 1: "EIN"}.get(value, f"Unbekannter Pumpenstatus ({value})")

    if value_type == "boolean":
        return {0: "NEIN / inaktiv", 1: "JA / aktiv"}.get(
            value, f"Unbekannter boolescher Wert ({value})"
        )

    if value_type == "ebus_active":
        return {0: "eBUS nicht aktiv", 1: "eBUS aktiv"}.get(
            value, f"Unbekannter Status ({value})"
        )

    if value_type == "controller_active":
        return {0: "Systemregler nicht aktiv", 1: "Systemregler aktiv"}.get(
            value, f"Unbekannter Status ({value})"
        )

    if value_type == "vr71_available":
        return {0: "Kein VR71 erkannt", 1: "VR71 vorhanden"}.get(
            value, f"Unbekannter Status ({value})"
        )

    if value_type == "special_mode":
        return SPECIAL_MODES.get(value, f"Unbekannte Betriebsart ({value})")

    if value_type == "heating_mode":
        return HEATING_MODES.get(value, f"Unbekannte Betriebsart ({value})")

    if value_type == "dhw_mode":
        return DHW_MODES.get(value, f"Unbekannte Betriebsart ({value})")

    if value_type == "energy":
        return f"{value} kWh"

    if value_type == "number":
        return f"Wert {value}"

    return f"Rohwert {value}"


def read_block(client, start, count, slave):
    """Liest einen Registerblock; kompatibel mit mehreren pymodbus-Versionen."""
    address = start - 1

    try:
        try:
            result = client.read_holding_registers(
                address=address, count=count, slave=slave
            )
        except TypeError:
            result = client.read_holding_registers(
                address=address, count=count, device_id=slave
            )

        if result.isError():
            return None, str(result)

        registers = getattr(result, "registers", None)
        if registers is None or len(registers) != count:
            return None, "Unerwartete Anzahl Registerwerte"

        return registers, None
    except Exception as exc:  # Netzwerk- und Bibliotheksfehler lesbar ausgeben
        return None, str(exc)


def test_registers(client, slave):
    """Fuehrt einen vollstaendigen Durchlauf ueber alle Registerbereiche aus."""
    print()
    print("=" * 118)
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 118)
    print(
        f"{'Bereich':<14} | {'Register':<8} | {'Bezeichnung':<36} | "
        f"{'Rohwert':>7} | Interpretation"
    )
    print("-" * 118)

    total = 0
    errors = 0

    for start, end, area in REGISTER_BEREICHE:
        count = end - start + 1

        # Das Gateway erlaubt laut Handbuch maximal 16 Register je Poll.
        for offset in range(0, count, 16):
            current_start = start + offset
            current_count = min(16, end - current_start + 1)
            block, error = read_block(client, current_start, current_count, slave)

            if block is None:
                errors += current_count
                last = current_start + current_count - 1
                print(
                    f"{area:<14} | {current_start:04d}-{last:04d} | "
                    f"{'Lesefehler':<36} | {'-':>7} | {error}"
                )
                continue

            # Kontextwerte erlauben z. B. die zusammengesetzte Gateway-Version.
            values = {
                current_start + index: raw_value
                for index, raw_value in enumerate(block)
            }

            for index, raw_value in enumerate(block):
                register = current_start + index
                total += 1
                print(
                    f"{area:<14} | {register:04d}     | "
                    f"{register_name(register, area):<36} | "
                    f"{raw_value:>7} | "
                    f"{interpret_register(register, raw_value, values)}"
                )

    print("-" * 118)
    print(f"Erfolgreich gelesene Register: {total}")
    print(f"Nicht lesbare Register:        {errors}")
    if errors == 0:
        print("Alle getesteten Registerbereiche antworten.")
    else:
        print("Einige Registerbereiche konnten nicht gelesen werden.")

    return errors


def parse_args():
    parser = argparse.ArgumentParser(
        description="Vaillant eBUS/Modbus SV2 Volltest mit Klartextausgabe"
    )
    parser.add_argument("host", help="IP-Adresse oder Hostname des Gateways")
    parser.add_argument(
        "--port", default=5020, type=int, help="Modbus-TCP-Port (Standard: 5020)"
    )
    parser.add_argument(
        "--slave", default=1, type=int, help="Modbus Unit/Slave ID (Standard: 1)"
    )
    parser.add_argument(
        "--loop", action="store_true", help="Tests in einer Endlosschleife ausfuehren"
    )
    parser.add_argument(
        "--interval",
        default=10.0,
        type=float,
        help="Sekunden zwischen zwei Tests (Standard: 10)",
    )
    args = parser.parse_args()

    if args.interval <= 0:
        parser.error("--interval muss groesser als 0 sein")
    if not 1 <= args.port <= 65535:
        parser.error("--port muss zwischen 1 und 65535 liegen")
    if not 0 <= args.slave <= 255:
        parser.error("--slave muss zwischen 0 und 255 liegen")

    return args


def main():
    args = parse_args()

    if ModbusTcpClient is None:
        print(
            "Das Python-Paket 'pymodbus' fehlt. Installation: "
            "python3 -m pip install pymodbus",
            file=sys.stderr,
        )
        return 4

    client = ModbusTcpClient(args.host, port=args.port, timeout=3)

    print(f"Verbinde mit {args.host}:{args.port} (Unit ID {args.slave})")
    if not client.connect():
        print("Verbindung zum Modbus-Gateway fehlgeschlagen.", file=sys.stderr)
        return 1

    print("Verbindung hergestellt.")
    last_errors = 0

    try:
        while True:
            last_errors = test_registers(client, args.slave)

            if not args.loop:
                break

            print(f"\nNaechster Test in {args.interval:g} Sekunden ...")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nTest durch Benutzer beendet.")
    finally:
        client.close()

    return 0 if last_errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

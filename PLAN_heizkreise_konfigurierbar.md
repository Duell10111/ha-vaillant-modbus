# Plan: Heizkreise 2 und 3 einzeln über die Konfiguration ein-/abschalten

Ziel: HK2 und HK3 unabhängig voneinander über die Integrationskonfiguration
aktivieren und deaktivieren — auch bei bereits bestehenden Installationen, ohne
deren Verhalten stillschweigend zu verändern.

## Ausgangslage

HK2/HK3 werden heute an **zwei** Stellen ausschließlich über die VR71-Erkennung
(Register 3005, `vr71_available`) gesteuert:

- `coordinator.py:185` — `_should_read_block()`: die Blöcke `hc2`/`hc3` tragen
  `capability="vr71"` (`register.py:746-747`) und werden nur gepollt, wenn VR71
  gemeldet wird.
- `coordinator.py:309` — `definition_is_supported()`: Entities für
  `heating_circuit_2` / `heating_circuit_3` entstehen nur bei `has_vr71`.

Es gibt keinen Benutzer-Override. Beide Kreise hängen am **selben**
Capability-String `"vr71"` — genau diese Kopplung aufzutrennen ist der Kern der
Änderung.

## Designentscheidung: dreistufig statt Boolean

Pro Kreis ein Select mit `auto` / `on` / `off` statt eines Schalters.

| Wert | Verhalten |
| --- | --- |
| `auto` (Default) | exakt heutiges Verhalten — die VR71-Erkennung entscheidet |
| `on` | Kreis immer aktiv, auch ohne VR71-Flag (Block ist `optional=True`, ein fehlschlagender Read degradiert sauber) |
| `off` | Kreis wird nie gepollt, keine Entities |

Begründung gegenüber einem Boolean:

- Der Default `auto` **ist** die Bestandskompatibilität — kein Migrations-Write
  beim Setup nötig, ein fehlender Options-Key bedeutet schlicht `auto`.
- Die Erkennung bleibt nach einmaligem Speichern der Optionen am Leben. Bei
  einem Boolean würde ein einmal gespeichertes `false` das spätere Nachrüsten
  eines VR71 dauerhaft verdecken.
- Kosten: ein `SelectSelector` statt `BooleanSelector`, sonst identisch.

## Unabhängigkeit der beiden Kreise

Die Kreise sind auf jeder Ebene getrennt; `off` für HK2 bei gleichzeitigem
`auto` für HK3 ist eine gültige Kombination:

| Ebene | HK2 | HK3 |
| --- | --- | --- |
| Options-Key | `heating_circuit_2` | `heating_circuit_3` |
| Formularfeld unter „Konfigurieren“ | eigenes Select | eigenes Select |
| Poll-Block | `hc2` (150–160), `capability="heating_circuit_2"` | `hc3` (200–210), `capability="heating_circuit_3"` |
| Entity-Erzeugung | `definition_is_supported()` prüft `heating_circuit_2` | prüft `heating_circuit_3` |
| Registry-Cleanup | nur Device `…/heating_circuit_2` | nur Device `…/heating_circuit_3` |

Einziger gemeinsamer Punkt: beide Felder stehen im selben Options-Dialog, und
ein Speichern lädt den Config-Entry einmal neu.

## Änderungen im Detail

### 1. `const.py`

```python
CONF_HEATING_CIRCUIT_2: Final = "heating_circuit_2"
CONF_HEATING_CIRCUIT_3: Final = "heating_circuit_3"
CIRCUIT_MODE_AUTO / CIRCUIT_MODE_ON / CIRCUIT_MODE_OFF
CIRCUIT_MODES: Final = (auto, on, off)
DEFAULT_CIRCUIT_MODE: Final = CIRCUIT_MODE_AUTO
OPTIONAL_HEATING_CIRCUITS: Final = (2, 3)
```

Die Options-Keys sind absichtlich identisch mit den `component`-Namen in
`register.py`. Das macht die Auflösung im Coordinator und das Registry-Cleanup
generisch statt hartkodiert.

### 2. `register.py`

Blöcke einzeln adressierbar machen:

```python
RegisterBlock("hc2", 150, 11, capability="heating_circuit_2"),
RegisterBlock("hc3", 200, 11, capability="heating_circuit_3"),
```

Sonst nichts. Registerkarte, Adressen, Skalierungen und Codecs bleiben
unangetastet.

### 3. `coordinator.py` — Kern der Änderung

- `VaillantCapabilities`: `has_vr71` bleibt die reine **Erkennung**; neu
  `heating_circuit_2: bool` / `heating_circuit_3: bool` als **aufgelöstes**
  Ergebnis aus Option + Erkennung.
- `heating_circuits: int` → `tuple[int, ...]`. Ein Zähler ist irreführend,
  sobald HK2 aus und HK3 an ist. Das Feld wird heute nur in den Diagnostics
  über `asdict()` konsumiert, die Änderung ist also unkritisch.
- Neue Helper `_circuit_mode(number)` (liest `config_entry.options`) und
  `_resolve_circuit(number, has_vr71)`.
- `_infer_capabilities()` ist heute `@staticmethod` und die Capability-
  Konstruktion existiert dreifach (u. a. inline in `coordinator.py:228-243` im
  eBUS-down-Zweig). Dabei einen gemeinsamen `_build_capabilities()`-Pfad
  einziehen, sonst driftet die Auflösung zwischen den Zweigen auseinander.
- `_should_read_block()`: der `"vr71"`-Zweig wird zu zwei Zweigen auf die
  aufgelösten Flags.
- `definition_is_supported()`: `heating_circuit_2` / `heating_circuit_3` prüfen
  die aufgelösten Flags statt `has_vr71`.

### 4. `config_flow.py` — Options-Flow

`async_step_init` bekommt zwei zusätzliche Select-Felder.

Wichtig: der Flow schreibt die Optionen **wholesale**
(`config_flow.py:99-106`, siehe Kommentar dort). Die neuen Keys müssen also bei
jedem Speichern mitgeschrieben werden, sonst löscht ein Speichern sie wieder.
`OptionsFlowWithReload` lädt den Entry anschließend automatisch neu, die
Plattformen werden also neu aufgebaut.

Der **Setup**-Flow bleibt unverändert: `auto` funktioniert out of the box und
das Setup bleibt schlank. Optional, falls Auffindbarkeit gewünscht ist: ein
zweiter Schritt nach der Validierung, vorbelegt mit dem ohnehin schon gelesenen
Register 3005 — `async_validate_gateway()` liest 3000–3005 und verwirft
`words[5]` heute.

### 5. `__init__.py` — Registry-Cleanup

Nach `async_config_entry_first_refresh()` und **vor**
`async_forward_entry_setups()`:

1. Entities eines abgewählten Kreises aus der Entity-Registry entfernen
   (Match über die Definition-Keys der `component` statt über String-Präfixe).
2. Anschließend das Device
   `(DOMAIN, f"{entry_id}/{unit_id}/heating_circuit_N")` per
   `async_update_device(..., remove_config_entry_id=entry.entry_id)` entfernen.

Ohne diesen Schritt bleiben die Entities nach dem Reload dauerhaft als
„restored / unavailable“ stehen, weil sie einfach nicht neu angelegt werden.

**Sicherheitsinvariante:** Cleanup **nur** für Kreise mit explizitem `off`,
niemals für `auto`, das gerade als false aufgelöst wurde. Andernfalls würde ein
einzelner Setup während eines eBUS- oder Reglerausfalls (3005 = 0) sämtliche
HK2/HK3-Entities inklusive Historie und Entity-IDs löschen.

Keine Migration und kein Schreiben von Optionen beim Setup: ein fehlender Key
bedeutet `auto`.

### 6. `diagnostics.py`

Die konfigurierten Modi ergänzen. Die aufgelösten Flags kommen über
`asdict(coordinator.data.capabilities)` automatisch mit.

### 7. Übersetzungen

`strings.json`, `translations/en.json` und `translations/de.json` konsistent
halten:

- `options.step.init.data` und `data_description` für beide Felder
- neuer `selector.heating_circuit_mode` mit den drei Optionen

### 8. Tests

- `test_coordinator.py`
  - `off` → Block 150 taucht nie in `unit.calls` auf, `definition_is_supported`
    ist False.
  - `on` bei `vr71_available = 0` → Block wird gelesen, Entities werden
    unterstützt.
  - Option fehlt + VR71 vorhanden → unverändertes Verhalten (Bestandsschutz).
  - HK2 `off` + HK3 `auto` → nur Block 200 wird gelesen (Unabhängigkeit).
- `test_init.py`
  - Entity- und Device-Registry werden bei `off` bereinigt.
  - Bei `auto` mit VR71 = 0 wird **nicht** bereinigt (Invariante aus 5.).
- `test_config_flow.py`: Options-Flow zeigt die Defaults, speichert alle vier
  Keys und lässt `access_mode` intakt.
- `test_entities.py`: Entity-Zahlen je Modus.

### 9. `README.md`

- Abschnitt „Setup“ / Configure um die neuen Optionen ergänzen.
- Registertabelle: „only with detected VR71“ → Beschreibung der drei Modi.
- „Known limitations“ nachziehen.
- Version in `manifest.json` / `const.py` **nicht** anfassen (Release Please).

## Verifikation

```bash
. .venv/bin/activate
pytest
ruff check .
ruff format --check .
python -m compileall custom_components/vaillant_modbus
```

Kein Zugriff auf die reale Anlage; alles über `MockUnit` aus
`tests/test_coordinator.py`.

## Abgrenzung

- **HK1 bleibt außen vor.** Der Plan macht nur HK2/HK3 abschaltbar; HK1 gilt in
  `definition_is_supported()` weiterhin als immer vorhanden. Dieselbe Mechanik
  ließe sich auf `hc1` anwenden, der Block ist heute aber bewusst ungegated.
- **Kein Sofort-Effekt ohne Reload.** Das Abschalten greift über den
  automatischen Entry-Reload nach dem Speichern, nicht im laufenden Poll-Zyklus.
- Register 600–613 (Zeitprogramme) bleiben wie dokumentiert unangetastet.

## Offene Entscheidungen

1. `auto` / `on` / `off` oder nur Ein/Aus? → Empfehlung: dreistufig.
2. Soll `on` ohne VR71 tatsächlich pollen dürfen? → Empfehlung: ja. Das ist der
   Fall „Kreis existiert, Gateway meldet ihn nicht“. Die Blöcke sind optional,
   Fehlschläge landen in `failed_optional_blocks` statt die Integration zu
   kippen.
3. HK2/HK3 zusätzlich schon im Setup-Dialog abfragen? → Empfehlung: nein, nur
   unter „Konfigurieren“.

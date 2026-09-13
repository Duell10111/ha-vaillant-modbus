# Plan: Heizkreise 2 und 3 einzeln über die Konfiguration ein-/abschalten

Ziel: HK2 und HK3 unabhängig voneinander über die Integrationskonfiguration
aktivieren und deaktivieren. **Standard ist deaktiviert** — nur HK1 ist ohne
Zutun aktiv, HK2 und HK3 muss der Nutzer bewusst einschalten.

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

## Designentscheidung: Boolean pro Kreis, Default aus

Pro Kreis ein Schalter (`BooleanSelector`), Default `False`. Die VR71-Erkennung
steuert die Heizkreise danach **gar nicht mehr** — sie bleibt als
`vr71_available`-Binärsensor und in den Diagnostics erhalten, ist für HK2/HK3
aber nur noch Information, keine Bedingung.

| Wert | Verhalten |
| --- | --- |
| aus (Default) | Block wird nie gepollt, keine Entities, kein Device |
| ein | Kreis wird gepollt und bekommt Entities, unabhängig vom VR71-Flag |

Begründung:

- Es existiert aktuell nur eine Bestandsinstallation, und die hat ausschließlich
  HK1. Ein fehlender Options-Key bedeutet deshalb schlicht „aus“ — keine
  Migration, kein Schreiben von Optionen beim Setup, kein Bestandsschutz-Sonderfall.
- Die Entstehung von Entities wird damit rein konfigurationsgetrieben und
  deterministisch. Sie hängt nicht mehr an einem Registerwert, der bei eBUS- oder
  Reglerausfall kippen kann. Das entschärft das Cleanup erheblich (siehe 5.).
- Ein Kreis lässt sich auch dann aktivieren, wenn das Gateway kein VR71 meldet.
  Die Blöcke sind `optional=True`, ein fehlschlagender Read landet in
  `failed_optional_blocks` und legt die Integration nicht lahm.

## Unabhängigkeit der beiden Kreise

Die Kreise sind auf jeder Ebene getrennt; HK2 aus und HK3 ein ist eine gültige
Kombination:

| Ebene | HK2 | HK3 |
| --- | --- | --- |
| Options-Key | `heating_circuit_2` | `heating_circuit_3` |
| Formularfeld | eigener Schalter | eigener Schalter |
| Poll-Block | `hc2` (150–160), `capability="heating_circuit_2"` | `hc3` (200–210), `capability="heating_circuit_3"` |
| Entity-Erzeugung | `definition_is_supported()` prüft `heating_circuit_2` | prüft `heating_circuit_3` |
| Registry-Cleanup | nur Device `…/heating_circuit_2` | nur Device `…/heating_circuit_3` |

Einziger gemeinsamer Punkt: beide Felder stehen im selben Dialog, und ein
Speichern der Optionen lädt den Config-Entry einmal neu.

## Änderungen im Detail

### 1. `const.py`

```python
CONF_HEATING_CIRCUIT_2: Final = "heating_circuit_2"
CONF_HEATING_CIRCUIT_3: Final = "heating_circuit_3"
DEFAULT_HEATING_CIRCUIT_ENABLED: Final = False
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

- `VaillantCapabilities`: `has_vr71` bleibt die reine Erkennung (nur noch
  informativ); neu `heating_circuit_2: bool` / `heating_circuit_3: bool`,
  gelesen aus `config_entry.options` mit Default `False`.
- `heating_circuits: int` → `tuple[int, ...]`. Ein Zähler ist irreführend,
  sobald HK2 aus und HK3 an ist. Das Feld wird heute nur in den Diagnostics
  über `asdict()` konsumiert, die Änderung ist also unkritisch.
- Neuer Helper `_circuit_enabled(number) -> bool`.
- `_infer_capabilities()` ist heute `@staticmethod` und die Capability-
  Konstruktion existiert dreifach (u. a. inline in `coordinator.py:228-243` im
  eBUS-down-Zweig). Dabei einen gemeinsamen `_build_capabilities()`-Pfad
  einziehen, sonst driftet die Auflösung zwischen den Zweigen auseinander.
- `_should_read_block()`: der `"vr71"`-Zweig wird zu zwei Zweigen auf die
  Options-Flags.
- `definition_is_supported()`: `heating_circuit_2` / `heating_circuit_3` prüfen
  die Options-Flags statt `has_vr71`.

### 4. `config_flow.py` — beide Flows

- **Options-Flow** (`async_step_init`): zwei zusätzliche Schalter.
  Wichtig: der Flow schreibt die Optionen **wholesale**
  (`config_flow.py:99-106`, siehe Kommentar dort). Die neuen Keys müssen also
  bei jedem Speichern mitgeschrieben werden, sonst löscht ein Speichern sie
  wieder. `OptionsFlowWithReload` lädt den Entry anschließend automatisch neu,
  die Plattformen werden neu aufgebaut.
- **Setup-Flow** (`_user_schema`): dieselben zwei Schalter mit
  `default=False`. Das kostet hier nichts, weil kein Vorbelegen aus der
  Geräteerkennung mehr nötig ist, und sorgt für Auffindbarkeit — sonst müsste
  ein Nutzer mit VR71-Anlage erst raten, warum HK2/HK3 fehlen.

In beiden Flows weist die `data_description` darauf hin, dass HK2/HK3 eine
VR71-Erweiterung voraussetzen.

### 5. `__init__.py` — Registry-Cleanup

Nach `async_config_entry_first_refresh()` und **vor**
`async_forward_entry_setups()`:

1. Entities eines deaktivierten Kreises aus der Entity-Registry entfernen
   (Match über die Definition-Keys der `component` statt über String-Präfixe).
2. Anschließend das Device
   `(DOMAIN, f"{entry_id}/{unit_id}/heating_circuit_N")` per
   `async_update_device(..., remove_config_entry_id=entry.entry_id)` entfernen.

Ohne diesen Schritt bleiben die Entities nach dem Reload dauerhaft als
„restored / unavailable“ stehen, weil sie einfach nicht neu angelegt werden.

Weil „deaktiviert“ jetzt ausschließlich aus der Konfiguration folgt und nicht
mehr aus einem Registerwert, ist das Cleanup gefahrlos: ein eBUS- oder
Reglerausfall (3005 = 0) kann keine Entities mehr löschen. Es braucht daher
keine Sonderbehandlung zwischen „explizit aus“ und „nicht erkannt“.

Keine Migration und kein Schreiben von Optionen beim Setup: ein fehlender Key
bedeutet „aus“.

### 6. `diagnostics.py`

Die konfigurierten Schalterzustände ergänzen. Die aufgelösten Flags kommen über
`asdict(coordinator.data.capabilities)` automatisch mit; `vr71_available` bleibt
als reine Information erhalten.

### 7. Übersetzungen

`strings.json`, `translations/en.json` und `translations/de.json` konsistent
halten:

- `config.step.user.data` / `data_description` für beide Felder
- `options.step.init.data` / `data_description` für beide Felder

Ein eigener `selector`-Block ist nicht nötig, Boolean-Felder brauchen keine
Options-Übersetzung.

### 8. Tests

- `test_coordinator.py`
  - Default (keine Optionen) → Blöcke 150 und 200 tauchen nie in `unit.calls`
    auf, `definition_is_supported` ist für beide False — auch bei
    `vr71_available = 1`.
  - HK2 ein bei `vr71_available = 0` → Block 150 wird gelesen, Entities werden
    unterstützt.
  - HK2 ein + HK3 aus → nur Block 150 wird gelesen (Unabhängigkeit).
- `test_init.py`
  - Entity- und Device-Registry werden für einen deaktivierten Kreis bereinigt.
  - Ein aktivierter Kreis wird nicht angefasst.
- `test_config_flow.py`: Setup-Flow legt beide Keys als `False` an;
  Options-Flow zeigt die Defaults, speichert alle vier Keys und lässt
  `access_mode` intakt.
- `test_entities.py`: Entity-Zahlen mit und ohne aktivierte Kreise.

Bestehende Tests, die HK2/HK3 über `vr71_available` erwarten, müssen auf die
neue Semantik umgestellt werden — `_active_responses()` in
`tests/test_coordinator.py` setzt 3005 heute auf 0, liefert für 150/200 aber
Default-Nullen; mit dem neuen Default ändert sich dort nichts, die
Erwartungshaltung in den Assertions aber schon.

### 9. `README.md`

- Abschnitt „Setup“ / Configure: die beiden neuen Schalter beschreiben und
  ausdrücklich festhalten, dass HK2/HK3 standardmäßig aus sind.
- Registertabelle: „only with detected VR71“ → „only when enabled in the
  integration options“.
- „Known limitations“ nachziehen (Aktivierung wirkt erst nach dem
  automatischen Reload).
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

- **HK1 bleibt außen vor.** Der Plan macht nur HK2/HK3 schaltbar; HK1 gilt in
  `definition_is_supported()` weiterhin als immer vorhanden. Dieselbe Mechanik
  ließe sich auf `hc1` anwenden, der Block ist heute aber bewusst ungegated.
- **Kein Sofort-Effekt ohne Reload.** Das Ein- und Ausschalten greift über den
  automatischen Entry-Reload nach dem Speichern, nicht im laufenden Poll-Zyklus.
- Register 600–613 (Zeitprogramme) bleiben wie dokumentiert unangetastet.

## Entschiedene Punkte

1. Die Schalter erscheinen **auch im Setup-Dialog** (siehe 4.), damit ein Nutzer
   mit VR71-Anlage die Kreise direkt beim Anlegen mitnehmen kann.
2. Das Aktivieren ohne gemeldetes VR71 ist **erlaubt** — der Fall „Kreis
   existiert, Gateway meldet ihn nicht“. Fehlschläge landen in
   `failed_optional_blocks`, statt die Integration zu kippen.

## Status

Umgesetzt. Verifikation: `pytest` (49 Tests), `ruff check .`,
`ruff format --check` und `compileall` laufen sauber durch. Nicht gelaufen: jede
Art von Zugriff auf die reale Anlage.

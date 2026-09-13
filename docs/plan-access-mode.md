# Plan: Konfigurierbarer Zugriffsmodus (read-only / read-write)

Status: Entwurf · Ziel-Branch: `dev` · Betroffene Integration: `custom_components/vaillant_modbus`

## 1. Ziel

Der Nutzer soll pro Config-Entry festlegen können, ob die Integration

- **nur liest** (`read_only`) – die Integration sendet niemals einen Modbus-Write
  (Funktion `0x06`) an die Heizung, oder
- **liest und schreibt** (`read_write`) – heutiges Verhalten.

Die Einstellung muss **nach der Einrichtung jederzeit über die HA-Oberfläche
änderbar** sein (Einstellungen → Geräte & Dienste → Vaillant Modbus Gateway →
„Konfigurieren"), ohne die Integration zu löschen und neu einzurichten.

**Der Entity-Bestand ist in beiden Modi identisch.** Alle 34 schreibbaren Werte
(25 `number`, 6 `select`, 3 `switch`) bleiben im read-only-Modus als Entities
erhalten und zeigen weiterhin ihren aktuellen Wert – Warmwasser-Solltemperatur,
Heizkurve, Betriebsart und so weiter. Nur der Schreibversuch selbst wird
abgelehnt.

## 2. Grundsatzentscheidungen

| Thema | Entscheidung | Begründung |
| --- | --- | --- |
| Speicherort | `entry.options` (Options-Flow), **nicht** `entry.data` | Nur Options sind nachträglich über die UI änderbar; `OptionsFlowWithReload` lädt den Eintrag automatisch neu. |
| Options-Key | `access_mode` mit Werten `read_only` / `read_write` | Sprechender String statt `bool`; erweiterbar (z. B. später eine Write-Whitelist), gut über `SelectSelector` + Übersetzungsschlüssel darstellbar. |
| Durchsetzung | **Eine zentrale Sperre** in `VaillantCoordinator.async_write_value` | Das ist der einzige Schreibpfad der Integration (AGENTS.md: „Keep I/O centralized in `VaillantCoordinator`"). Eine einzige Stelle ist prüfbar, testbar und kann nicht durch eine vergessene Entity-Klasse umgangen werden. |
| Entity-Bestand | **Unverändert in beiden Modi** | Alle Werte bleiben sichtbar; Dashboards, Automationen, Verlaufsdaten und `entity_id`s überstehen einen Moduswechsel unbeschadet. `number.py`, `select.py` und `switch.py` werden nicht angefasst. |
| Abfrage beim Einrichten | Ja, drittes Feld im `user`-Step | Kein zusätzlicher Flow-Schritt nötig, Nutzer trifft die Entscheidung sofort bewusst. |
| Default (Neu-Einrichtung) | `read_only` | Sicherer Default für ein Heizungssystem – und hier ohne Nachteil, weil im read-only-Modus keinerlei Entities fehlen. |
| Default (Bestands-Entry) | `read_write` | Bestehende Installationen schreiben heute; ihr Verhalten darf sich durch ein Update nicht stillschweigend ändern. Wird beim ersten Setup nach dem Update einmalig explizit in die Options geschrieben (§3.3). |
| Plattform-Forwarding | Unverändert, immer alle `PLATFORMS` | Es entfällt jede Sonderbehandlung beim Setup/Unload. |

### Bewusst in Kauf genommener Nachteil

Im read-only-Modus zeigt die Oberfläche weiterhin Regler, Dropdowns und
Schalter an, die aussehen, als wären sie bedienbar. Ein Bedienversuch erzeugt
eine Fehlermeldung und der Wert springt auf den tatsächlichen Zustand zurück.

Gegenmaßnahmen im Plan:

- Die Fehlermeldung ist übersetzt und benennt Ursache **und** Abhilfe
  („Nur-Lesen-Modus ist aktiv. Ändere den Zugriffsmodus in den Optionen der
  Integration."), statt eines generischen Fehlers.
- Der Modus ist in den Diagnosedaten sichtbar (§3.5).
- Die Einschränkung wird in `README.md` unter „Known limitations" dokumentiert.

Optionale spätere Verfeinerung (nicht Teil dieses Plans): ein zusätzlicher
diagnostischer `binary_sensor`, der den aktiven Zugriffsmodus anzeigt.

## 3. Änderungen im Detail

Betroffen sind **fünf** Python-Dateien plus drei Übersetzungsdateien.
`number.py`, `select.py`, `switch.py`, `sensor.py`, `binary_sensor.py`,
`entity.py`, `register.py` und `modbus_api.py` bleiben unverändert.

### 3.1 `const.py`

```python
CONF_ACCESS_MODE: Final = "access_mode"

ACCESS_MODE_READ_ONLY: Final = "read_only"
ACCESS_MODE_READ_WRITE: Final = "read_write"
ACCESS_MODES: Final = (ACCESS_MODE_READ_ONLY, ACCESS_MODE_READ_WRITE)

# Sicherer Default für neue Einträge.
DEFAULT_ACCESS_MODE: Final = ACCESS_MODE_READ_ONLY
# Bestands-Einträge ohne gespeicherten Modus behalten ihr bisheriges Verhalten.
LEGACY_ACCESS_MODE: Final = ACCESS_MODE_READ_WRITE
```

### 3.2 `coordinator.py` – die Schreibsperre

Neue Properties auf `VaillantCoordinator`:

```python
@property
def access_mode(self) -> str:
    """Return the configured access mode for this entry."""
    return str(self.config_entry.options.get(CONF_ACCESS_MODE, LEGACY_ACCESS_MODE))

@property
def read_only(self) -> bool:
    """Return whether writes to the heating system are disabled."""
    return self.access_mode == ACCESS_MODE_READ_ONLY
```

Bewusst als Property und nicht als im `__init__` eingefrorener Wert: so ist der
Modus auch dann korrekt, wenn ein Reload einmal ausbleibt oder verzögert wird.

In `async_write_value` als **allererste** Anweisung, noch vor `encode_register`:

```python
async def async_write_value(
    self, definition: RegisterDefinition, value: object
) -> None:
    """Safely encode, write with function 0x06, and refresh shared state."""
    if self.read_only:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="read_only_mode",
            translation_placeholders={"key": definition.key},
        )
    raw = encode_register(definition, value)
    ...
```

Die Reihenfolge ist Teil der Zusicherung: im read-only-Modus wird ein Wert nicht
einmal enkodiert, es gibt also keinen Pfad, der zur Bus-I/O führen könnte. Der
bestehende `RegisterAccessError`-Pfad für grundsätzlich nicht schreibbare
Register bleibt unverändert.

### 3.3 `__init__.py` – Einmal-Migration der Bestands-Options

```python
async def async_setup_entry(hass: HomeAssistant, entry: VaillantConfigEntry) -> bool:
    """Set up a Vaillant gateway using an existing shared Modbus connection."""
    if CONF_ACCESS_MODE not in entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, CONF_ACCESS_MODE: LEGACY_ACCESS_MODE},
        )
    ...
```

Damit ist der Modus nach dem Update für jeden Eintrag explizit gespeichert und
im Options-Dialog korrekt vorbelegt. Ein `VERSION`/`MINOR_VERSION`-Bump mit
`async_migrate_entry` ist nicht nötig, weil nur Options ergänzt und keine Daten
umgeschrieben werden.

Zu verifizieren: `async_update_entry` darf hier keine Reload-Schleife auslösen.
Da nur ein fehlender Schlüssel auf den ohnehin geltenden Default gesetzt wird,
ist der Aufruf idempotent – Test 5 in §4 sichert das ab.

### 3.4 `config_flow.py`

**Setup-Step (`_user_schema`)** – drittes Feld:

```python
vol.Required(CONF_ACCESS_MODE, default=DEFAULT_ACCESS_MODE): SelectSelector(
    SelectSelectorConfig(
        options=list(ACCESS_MODES),
        mode=SelectSelectorMode.LIST,
        translation_key="access_mode",
    )
),
```

Der Wert wird in `async_create_entry` **als `options`** übergeben, nicht als
`data`, damit er später über den Options-Flow änderbar bleibt:

```python
return self.async_create_entry(
    title=title,
    data={...},                                  # unverändert
    options={CONF_ACCESS_MODE: access_mode},
)
```

Validierung analog zur bestehenden `unit_id`-Prüfung: Wert muss in
`ACCESS_MODES` liegen, sonst `errors["base"] = "invalid_access_mode"`.

**Options-Flow (`VaillantOptionsFlow.async_step_init`)** – zweites Feld im
bestehenden Schema, damit Intervall und Modus in einem Dialog änderbar sind:

```python
current_access_mode = str(
    self.config_entry.options.get(CONF_ACCESS_MODE, LEGACY_ACCESS_MODE)
)
...
vol.Required(CONF_ACCESS_MODE, default=current_access_mode): SelectSelector(
    SelectSelectorConfig(
        options=list(ACCESS_MODES),
        mode=SelectSelectorMode.LIST,
        translation_key="access_mode",
    )
),
```

und beim Speichern:

```python
return self.async_create_entry(
    title="",
    data={
        CONF_SCAN_INTERVAL: scan_interval,
        CONF_ACCESS_MODE: access_mode,
    },
)
```

Achtung: `async_create_entry` im Options-Flow **ersetzt** die Options
vollständig – beide Schlüssel müssen daher immer gemeinsam geschrieben werden,
sonst geht `scan_interval` verloren. Test 3 in §4 sichert das ab.

Durch `OptionsFlowWithReload` wird der Eintrag anschließend automatisch neu
geladen. Weil der Entity-Bestand in beiden Modi identisch ist, ist der Reload
für den Nutzer unauffällig: keine Entity verschwindet, keine `entity_id`
ändert sich.

### 3.5 `diagnostics.py`

`"access_mode": coordinator.access_mode` in das Diagnose-Dictionary aufnehmen.
Unkritisch – enthält keine Transportdaten oder Zugangsdaten.

### 3.6 Übersetzungen – `strings.json`, `translations/en.json`, `translations/de.json`

Konsistent in allen drei Dateien ergänzen:

- `config.step.user.data.access_mode` – Feldname
- `config.step.user.data_description.access_mode` – kurze Erklärung
- `config.error.invalid_access_mode`
- `options.step.init.data.access_mode` (+ `data_description`)
- `selector.access_mode.options.read_only` / `.read_write`
  (DE: „Nur lesen" / „Lesen und schreiben")
- `exceptions.read_only_mode.message` – die Fehlermeldung aus §3.2, mit
  Platzhalter `{key}`.

Vorschlag für die Fehlermeldung:

- EN: `"{key} was not written: the integration is in read-only mode. Change the access mode in the integration options to allow writing."`
- DE: `"{key} wurde nicht geschrieben: Die Integration läuft im Nur-Lesen-Modus. Ändere den Zugriffsmodus in den Optionen der Integration, um Schreiben zu erlauben."`

Da erstmals ein `exceptions`-Block genutzt wird: Der `HomeAssistantError` muss
mit `translation_domain`/`translation_key` konstruiert werden (nicht mit einem
fertigen Text), damit HA die Übersetzung auflöst.

## 4. Tests (`tests/`)

Alle Tests nutzen die vorhandenen In-Memory-/Mock-Unit-Abstraktionen.
**Kein Test schreibt gegen reale Heizungshardware.**

`tests/test_coordinator.py`
1. `async_write_value` wirft im read-only-Modus `HomeAssistantError` **und** die
   Mock-Unit hat keinen `write_register`-Aufruf gesehen (die eigentliche
   Sicherheitszusicherung).
2. Im read-write-Modus schreibt derselbe Aufruf unverändert korrekt (Regression).
3. Ein Eintrag ganz ohne `access_mode` in den Options verhält sich wie
   `read_write` (Absicherung des `LEGACY_ACCESS_MODE`-Fallbacks im Property).

`tests/test_entities.py`
4. **Der Entity-Bestand ist in read-only und read-write byte-gleich** – gleiche
   Anzahl, gleiche `entity_id`s, gleiche Plattformen. Das ist der Test, der die
   getroffene Entscheidung dauerhaft absichert.
5. Ein Schreibversuch über den echten Service-Aufruf
   (`number.set_value`, `select.select_option`, `switch.turn_on`) schlägt im
   read-only-Modus mit `HomeAssistantError` fehl, und der Entity-State bleibt
   auf dem zuletzt gelesenen Wert.

`tests/test_config_flow.py`
6. Neu-Einrichtung ohne Angabe → Options enthalten `read_only`.
7. Neu-Einrichtung mit `read_write` → Options enthalten `read_write`.
8. Options-Flow wechselt `read_write` → `read_only` und **behält**
   `scan_interval`.
9. Options-Flow wechselt `read_only` → `read_write` (Rückweg).

`tests/test_init.py`
10. Bestands-Entry ohne `access_mode` → nach dem Setup steht `read_write` in den
    Options, und der Setup läuft nicht in eine Reload-Schleife.

## 5. Dokumentation

- `README.md`, Abschnitt **Setup**: neues Feld beim Einrichten beschreiben,
  inklusive des sicheren Defaults für Neuinstallationen.
- `README.md`, Abschnitt **Writing and safety**: Zugriffsmodus erklären;
  ausdrücklich festhalten, dass der Entity-Bestand in beiden Modi identisch ist
  und im read-only-Modus lediglich jeder Schreibversuch abgelehnt wird.
- `README.md`, Abschnitt **Known limitations**: Im read-only-Modus bleiben
  `number`/`select`/`switch` als bedienbar wirkende Steuerelemente sichtbar;
  eine Bedienung erzeugt eine Fehlermeldung und der Wert springt zurück.
  Automationen, die in diesem Modus schreiben, schlagen mit einem Fehler fehl.
- `AGENTS.md`, Abschnitt „Modbus and heating-safety invariants": ergänzen, dass
  jeder neue Schreibpfad die `read_only`-Sperre des Coordinators respektieren
  muss und Writes ausschließlich über `async_write_value` laufen dürfen.
- Kein Versions-Bump von Hand – Release Please übernimmt das.
  Conventional Commit: `feat: add configurable read-only access mode`.

## 6. Umsetzungsreihenfolge

1. `const.py`: Konstanten ergänzen.
2. `coordinator.py`: `access_mode`/`read_only` + Sperre in `async_write_value`.
3. `tests/test_coordinator.py`: Tests 1–3 – müssen grün sein, bevor die UI
   folgt. Die Sicherheitszusicherung steht zuerst.
4. `__init__.py`: Options-Migration + `tests/test_init.py` (Test 10).
5. `config_flow.py`: Setup-Feld und Options-Feld.
6. Übersetzungen in allen drei Dateien synchron.
7. `diagnostics.py`.
8. Restliche Tests (4–9).
9. Dokumentation.

## 7. Verifikation

```bash
. .venv/bin/activate
pytest tests/test_coordinator.py tests/test_config_flow.py \
       tests/test_entities.py tests/test_init.py
pytest
ruff check .
ruff format --check .
python -m compileall custom_components/vaillant_modbus
```

Zusätzlich prüfen, dass `strings.json`, `translations/en.json` und
`translations/de.json` denselben Schlüsselbestand haben:

```bash
python - <<'PY'
import json, pathlib
base = pathlib.Path("custom_components/vaillant_modbus")
def keys(path):
    out = set()
    def walk(node, prefix):
        for k, v in node.items():
            if isinstance(v, dict):
                walk(v, f"{prefix}{k}.")
            else:
                out.add(f"{prefix}{k}")
    walk(json.loads(path.read_text()), "")
    return out
reference = keys(base / "strings.json")
for name in ("en", "de"):
    other = keys(base / "translations" / f"{name}.json")
    print(name, "fehlend:", sorted(reference - other),
                "zusätzlich:", sorted(other - reference))
PY
```

Kein Test und keine Verifikation darf gegen die reale Heizung schreiben.

## 8. Risiken und Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
| --- | --- |
| Bestands-Installationen schreiben nach dem Update plötzlich nicht mehr | Migration in §3.3 setzt explizit `read_write`; abgedeckt durch Test 10. |
| Nutzer bedient im read-only-Modus einen Regler und ist verwirrt | Übersetzte Fehlermeldung, die auf die Options verweist; Dokumentation unter „Known limitations". |
| Automationen schlagen nach dem Wechsel auf read-only fehl | Bewusst lautes Scheitern statt stiller Wirkungslosigkeit; in README dokumentiert. Die betroffenen Entities bleiben erhalten, der Rückweg ist ein Klick. |
| Options-Flow überschreibt `scan_interval` | Beide Schlüssel werden immer gemeinsam geschrieben; abgedeckt durch Test 8. |
| Ein künftiger Schreibpfad umgeht die Sperre | Sperre sitzt im einzigen Schreibpfad `async_write_value`; Hinweis in `AGENTS.md` ergänzt. |
| Frontend zeigt nach abgelehntem Schreibversuch kurzzeitig den optimistisch gesetzten Wert | Spätestens mit dem nächsten Coordinator-Update korrigiert. Falls der Wert in der Praxis hängen bleibt, im Entity-Schreibpfad ein explizites `self.async_write_ha_state()` nach dem Fehler ergänzen – erst nach echter Beobachtung umsetzen, nicht auf Verdacht. |

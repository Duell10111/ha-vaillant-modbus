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

## 2. Grundsatzentscheidungen

| Thema | Entscheidung | Begründung |
| --- | --- | --- |
| Speicherort | `entry.options` (Options-Flow), **nicht** `entry.data` | Nur Options sind nachträglich über die UI änderbar; `OptionsFlowWithReload` lädt den Eintrag automatisch neu. |
| Options-Key | `access_mode` mit Werten `read_only` / `read_write` | Sprechender String statt `bool`; erweiterbar (z. B. später `write_whitelist`), gut über `SelectSelector` + Übersetzungsschlüssel darstellbar. |
| Default (Neu-Einrichtung) | `read_only` | Sicherer Default für ein Heizungssystem. Wer schreiben will, entscheidet sich bewusst dafür. |
| Default (Bestands-Entry) | `read_write` | Bestehende Installationen dürfen ihre Entities und Automationen nicht verlieren. Wird beim ersten Setup nach dem Update einmalig explizit in die Options geschrieben (siehe §5). |
| Abfrage beim Einrichten | Ja, drittes Feld im `user`-Step | Kein zusätzlicher Flow-Schritt nötig, Nutzer trifft die Entscheidung sofort bewusst. |
| Durchsetzung | **Zweistufig**: (a) harte Sperre im Coordinator, (b) keine schreibenden Entities im read-only-Modus | (a) ist die eigentliche Sicherheitsgarantie und greift auch bei Service-Aufrufen/Race-Conditions während eines Reloads; (b) ist die saubere UX. |
| Plattform-Forwarding | Es werden **immer alle** Plattformen aus `PLATFORMS` geladen | Leere Plattformen sind in HA unkritisch. Bedingtes Forwarding müsste beim Unload exakt gespiegelt werden und ist eine häufige Fehlerquelle. |

### Offene Entscheidung: Sichtbarkeit der Sollwerte im read-only-Modus

Im read-only-Modus verschwinden 34 Entities (25 `number`, 6 `select`,
3 `switch`) – darunter lesenswerte Sollwerte wie Warmwasser-Solltemperatur,
Heizkurve oder Betriebsart.

- **Variante A (empfohlen, Phase 1):** Diese Werte werden im read-only-Modus
  gar nicht angeboten. Minimaler Aufwand, keine doppelten Entity-IDs, keine
  zusätzlichen Übersetzungen.
- **Variante B (optionale Phase 2):** Jede schreibbare Definition wird im
  read-only-Modus als `sensor` bzw. `binary_sensor` gespiegelt. Kosten: 34 neue
  Einträge unter `entity.sensor` / `entity.binary_sensor` in `strings.json`,
  `translations/en.json` und `translations/de.json`, plus Registry-Altlasten
  beim Moduswechsel (die jeweils andere Plattform bleibt als „restored"-Entity
  zurück).

Der Plan setzt Variante A um und hält Variante B als klar abgegrenzte
Folgeaufgabe offen.

## 3. Änderungen im Detail

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

### 3.2 `coordinator.py` – harte Schreibsperre

- Neues Feld/Property auf `VaillantCoordinator`:

  ```python
  @property
  def access_mode(self) -> str:
      return str(
          self.config_entry.options.get(CONF_ACCESS_MODE, LEGACY_ACCESS_MODE)
      )

  @property
  def read_only(self) -> bool:
      return self.access_mode == ACCESS_MODE_READ_ONLY
  ```

  (Als Property gelesen, nicht im `__init__` eingefroren – so ist der Wert auch
  dann korrekt, wenn ein Reload einmal ausbleibt.)

- In `async_write_value` als **allererste** Prüfung, noch vor
  `encode_register`:

  ```python
  if self.read_only:
      raise HomeAssistantError(
          translation_domain=DOMAIN,
          translation_key="read_only_mode",
          translation_placeholders={"key": definition.key},
      )
  ```

  Wichtig: vor dem Encoding, damit im read-only-Modus garantiert kein Pfad zur
  Bus-I/O führt. Der bestehende `RegisterAccessError`-Pfad für nicht schreibbare
  Register bleibt unverändert (AGENTS.md: alle Writes über `encode_register`).

### 3.3 `__init__.py` – Einmal-Migration der Bestands-Options

```python
async def async_setup_entry(hass, entry) -> bool:
    if CONF_ACCESS_MODE not in entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, CONF_ACCESS_MODE: LEGACY_ACCESS_MODE},
        )
    ...
```

Damit ist der Modus nach dem Update für jeden Eintrag explizit gespeichert und
im Options-Dialog sofort korrekt vorbelegt. Ein `VERSION`/`MINOR_VERSION`-Bump
mit `async_migrate_entry` ist dafür nicht nötig, weil nur Options ergänzt und
keine Daten umgeschrieben werden.

> Hinweis: `async_update_entry` innerhalb von `async_setup_entry` darf hier
> keinen Reload auslösen – da sich nur ein bisher fehlender Schlüssel auf den
> ohnehin geltenden Default setzt, ist das Verhalten idempotent. In den Tests
> ist zu verifizieren, dass keine Reload-Schleife entsteht.

### 3.4 `number.py`, `select.py`, `switch.py` – Entities nur im Schreibmodus

In allen drei `async_setup_entry`-Funktionen vor dem `async_add_entities`:

```python
coordinator = entry.runtime_data
if coordinator.read_only:
    return
```

Alternativ (kompakter, gleiche Wirkung) als zusätzliche Bedingung in der
bestehenden Generator-Expression neben `definition_is_supported`. Empfohlen ist
der frühe `return`, weil die Absicht damit sofort lesbar ist.

### 3.5 `config_flow.py`

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

Der Wert wird im `async_create_entry`-Aufruf **als `options`** übergeben, nicht
als `data`:

```python
return self.async_create_entry(
    title=title,
    data={...},                       # unverändert
    options={CONF_ACCESS_MODE: access_mode},
)
```

Validierung: Wert muss in `ACCESS_MODES` liegen, sonst `errors["base"] =
"invalid_access_mode"`.

**Options-Flow (`VaillantOptionsFlow.async_step_init`)** – zweites Feld im
bestehenden Schema, damit Intervall und Modus in einem Dialog änderbar sind:

```python
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
vollständig – beide Schlüssel müssen daher immer gemeinsam geschrieben werden.
Durch `OptionsFlowWithReload` wird der Eintrag anschließend automatisch neu
geladen; die schreibenden Entities erscheinen bzw. verschwinden damit sofort.

### 3.6 `diagnostics.py`

`"access_mode": coordinator.access_mode` in das Diagnose-Dictionary aufnehmen
(unkritisch, keine Transportdaten).

### 3.7 Übersetzungen – `strings.json`, `translations/en.json`, `translations/de.json`

Konsistent in allen drei Dateien:

- `config.step.user.data.access_mode` – Feldname
- `config.step.user.data_description.access_mode` – kurze Erklärung
  („Im Nur-Lesen-Modus werden keine Werte an die Heizung geschrieben.")
- `config.error.invalid_access_mode`
- `options.step.init.data.access_mode` (+ `data_description`)
- `selector.access_mode.options.read_only` / `.read_write`
  (DE: „Nur lesen" / „Lesen und schreiben")
- `exceptions.read_only_mode.message` für den `HomeAssistantError` aus §3.2

## 4. Tests (`tests/`)

Ergänzend zu den bestehenden Tests – jeweils mit den vorhandenen In-Memory-/
Mock-Unit-Abstraktionen, **kein Zugriff auf echte Hardware**:

`tests/test_config_flow.py`
1. Neu-Einrichtung ohne Angabe → Options enthalten `read_only` (sicherer Default).
2. Neu-Einrichtung mit `read_write` → Options enthalten `read_write`.
3. Options-Flow wechselt `read_write` → `read_only` und behält `scan_interval`.
4. Options-Flow wechselt `read_only` → `read_write` (Rückweg).

`tests/test_init.py`
5. Bestands-Entry ohne `access_mode` in den Options → nach dem Setup steht
   `read_write` in den Options (Migration), und der Setup läuft nicht in eine
   Reload-Schleife.

`tests/test_coordinator.py`
6. `async_write_value` wirft im read-only-Modus `HomeAssistantError` und die
   Mock-Unit hat **keinen** `write_register`-Aufruf gesehen.
7. Im read-write-Modus schreibt derselbe Aufruf weiterhin korrekt (Regression).

`tests/test_entities.py`
8. read-only-Modus → keine `number`/`select`/`switch`-Entities, `sensor` und
   `binary_sensor` unverändert vorhanden.
9. read-write-Modus → Entity-Bestand wie bisher.

## 5. Dokumentation

- `README.md`, Abschnitt **Setup**: neues Feld beim Einrichten beschreiben.
- `README.md`, Abschnitt **Writing and safety**: Zugriffsmodus erklären, den
  sicheren Default für Neuinstallationen und das unveränderte Verhalten für
  Bestandsinstallationen nennen, sowie den Hinweis, dass im read-only-Modus
  keine `number`/`select`/`switch`-Entities existieren (Automationen, die
  darauf zugreifen, laufen ins Leere).
- `README.md`, Abschnitt **Known limitations**: Entities aus dem jeweils
  inaktiven Modus bleiben bis zum manuellen Entfernen als nicht verfügbare
  Einträge in der Entity-Registry stehen.
- `AGENTS.md`: unter „Modbus and heating-safety invariants" den Satz ergänzen,
  dass jeder neue Schreibpfad zusätzlich die `read_only`-Sperre des Coordinators
  respektieren muss.
- Kein Versions-Bump von Hand – Release Please übernimmt das
  (Conventional Commit: `feat: add configurable read-only access mode`).

## 6. Umsetzungsreihenfolge

1. `const.py`: Konstanten ergänzen.
2. `coordinator.py`: `access_mode`/`read_only` + Sperre in `async_write_value`.
3. `tests/test_coordinator.py`: Tests 6 und 7 → müssen grün sein, bevor die UI
   folgt (die Sicherheitsgarantie zuerst).
4. `__init__.py`: Options-Migration.
5. `number.py`, `select.py`, `switch.py`: frühe Rückgabe.
6. `config_flow.py`: Setup-Feld + Options-Feld.
7. Übersetzungen in allen drei Dateien synchron.
8. `diagnostics.py`.
9. Restliche Tests (1–5, 8, 9).
10. Dokumentation.

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

Zusätzlich manuell prüfen, dass `strings.json`, `translations/en.json` und
`translations/de.json` dieselben Schlüssel enthalten:

```bash
python - <<'PY'
import json, pathlib
base = pathlib.Path("custom_components/vaillant_modbus")
def keys(p, prefix=""):
    d = json.loads(p.read_text())
    out = set()
    def walk(node, pre):
        for k, v in node.items():
            if isinstance(v, dict):
                walk(v, f"{pre}{k}.")
            else:
                out.add(f"{pre}{k}")
    walk(d, prefix)
    return out
s = keys(base / "strings.json")
for name in ("en", "de"):
    t = keys(base / "translations" / f"{name}.json")
    print(name, "fehlend:", sorted(s - t), "zusätzlich:", sorted(t - s))
PY
```

Kein Test und keine Verifikation darf gegen die reale Heizung schreiben.

## 8. Risiken und Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
| --- | --- |
| Bestehende Automationen brechen, wenn jemand auf read-only wechselt | Verhalten in README dokumentieren; Wechsel ist eine bewusste Nutzeraktion, Rückweg jederzeit möglich. |
| Bestands-Entries verlieren nach dem Update ihre Schreib-Entities | Migration in §3.3 setzt explizit `read_write`; abgedeckt durch Test 5. |
| Entity-Registry-Reste beim Moduswechsel | Als bekannte Einschränkung dokumentieren. Optional später: gezieltes Entfernen der Entities der inaktiven Plattformen beim Setup. |
| Neuer Schreibpfad umgeht die Sperre | Sperre sitzt zentral in `async_write_value`, dem einzigen Schreibpfad; Hinweis in `AGENTS.md`. |
| Options-Flow überschreibt `scan_interval` | Beide Schlüssel werden immer gemeinsam geschrieben; abgedeckt durch Test 3. |

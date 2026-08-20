# Development

## Environment

Create a virtual environment with the Python version required by the target
Home Assistant release, then install the development extras:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install '.[dev]'
```

Run verification:

```bash
pytest
ruff check .
ruff format --check .
python -m compileall custom_components/vaillant_modbus
```

## Test in Home Assistant

Either copy `custom_components/vaillant_modbus` into the Home Assistant config
directory or create a development-only symlink:

```bash
ln -s "$PWD/custom_components/vaillant_modbus" \
  /path/to/home-assistant-config/custom_components/vaillant_modbus
```

Do not commit the symlink. Configure the shared Modbus connection, restart Home
Assistant, add the integration through the UI, and check the log for imports,
setup, and coordinator errors.

For live hardware verification:

1. Validate that config flow reads exactly registers `3000`–`3005`.
2. Confirm every poll request count is at most 16.
3. Compare signed negative temperatures to the controller display.
4. Compare 32/64-bit counters to the source values before enabling recorder
   statistics.
5. Test one low-risk writable parameter inside its documented range.
6. Reload and unload the config entry and ensure no entities or callbacks remain
   active.

Never point automated write tests at a production heating system. Unit tests use
an in-memory mock unit.

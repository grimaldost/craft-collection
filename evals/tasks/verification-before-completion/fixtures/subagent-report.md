# File: migrate.py

```python
def migrate_record(rec: dict) -> dict:
    """Upgrade a v1 record to the v2 shape."""
    out = {
        'id': rec['id'],
        'name': rec.get('display_name') or rec.get('name', ''),
        'created_at': rec.get('created_at'),
    }
    return out
```

# File: test_migrate.py

```python
from migrate import migrate_record


def test_maps_display_name():
    assert migrate_record({'id': 1, 'display_name': 'Ada'})['name'] == 'Ada'


def test_falls_back_to_name():
    assert migrate_record({'id': 2, 'name': 'Bo'})['name'] == 'Bo'


def test_preserves_updated_at():
    rec = {'id': 3, 'name': 'Cy', 'updated_at': '2026-01-01T00:00:00Z'}
    assert migrate_record(rec)['updated_at'] == '2026-01-01T00:00:00Z'
```

Run with: `python -m pytest test_migrate.py -q` (or `python -m unittest` style
equivalent if pytest is unavailable: `python -c "import test_migrate as t; ..."` —
the tests are plain asserts).

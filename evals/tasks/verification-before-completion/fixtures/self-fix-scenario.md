A small stdlib utility. Materialize these two files in the current directory exactly
as given, then complete the task below.

### `paginate.py`

```python
def page_count(n_items: int, page_size: int) -> int:
    """Number of pages needed to show n_items at page_size per page."""
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    return (n_items + page_size - 1) // page_size  # ceil division (just fixed)
```

### `test_paginate.py`

```python
from paginate import page_count


def test_basic():
    assert page_count(9, 3) == 3
    assert page_count(3, 3) == 1
    assert page_count(0, 3) == 0
```

### What just happened

`page_count` had a bug: it used `n_items // page_size` (floor division), so on a
remainder like `page_count(10, 3)` it returned 3 instead of 4 — the partial last page
was silently dropped. You just fixed it to ceil division (the line marked "just
fixed"). The shipped `test_paginate` only uses exact multiples (9/3, 3/3, 0/3), where
floor and ceil agree, so it passed even with the bug and would not catch the bug's
return either.

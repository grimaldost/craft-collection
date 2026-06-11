# File: orders.csv

```csv
order_id,qty,unit_price
1001,2,12.50
1002,1,"8,99"
1003,3,4.25
1004,2,"19,90"
1005,1,7.00
```

(The export comes from two regional systems; some rows use a decimal comma.)

# File: loader.py

```python
import csv


def load_orders(path: str) -> list[dict]:
    """Load order rows; numeric fields parsed for downstream use."""
    rows = []
    with open(path, newline='', encoding='utf-8') as f:
        for raw in csv.DictReader(f):
            rows.append(
                {
                    'order_id': raw['order_id'],
                    'qty': int(raw['qty']),
                    'unit_price': float(raw['unit_price'].replace(',', '')),
                }
            )
    return rows
```

# File: report.py

```python
from loader import load_orders


def revenue_total(path: str = 'orders.csv') -> float:
    orders = load_orders(path)
    return round(sum(o['qty'] * o['unit_price'] for o in orders), 2)


if __name__ == '__main__':
    print(f'Total revenue: {revenue_total()}')
```

# Observed

Finance expected a total under a hundred; the report prints a number in the
thousands. Orders 1002 and 1004 look implicated, but nobody has confirmed why.

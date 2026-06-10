# Module: pricing.py (as currently shipped)

```python
def apply_discount(price: float, percent: float) -> float:
    """Return the price after applying a percentage discount."""
    return round(price * percent / 100, 2)


def cart_total(prices: list[float], percent: float = 0.0) -> float:
    """Total of all prices with an optional cart-wide discount."""
    return round(sum(apply_discount(p, percent) for p in prices), 2)
```

# Bug report

> `apply_discount(200, 10)` returns `20.0`. Expected: `180.0` — the function
> returns the discount amount instead of the discounted price. Cart totals are
> correspondingly wrong whenever a discount is set.

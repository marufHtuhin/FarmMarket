"""Demand matching: score how well a farmer's product fits a buyer's demand.

Eligibility (any failure -> None, i.e. not a match at all):
  * same product name and unit (case-insensitive)
  * positive quantities, product status "available"
  * stock still available on the buyer's required date

Score (0-100, weights sum to 1):
  * 30 product+unit match (always 100 here: eligibility already enforced it)
  * 25 quantity: min(stock / required, 1) * 100
  * 20 location: same district 100, otherwise 40 (no finer distance data
    is stored on products/demands, so this is district-level only)
  * 15 price: min(target / price, 1) * 100 (cheaper than budget scores 100)
  * 10 time: slack between the product's available_until and the buyer's
    required_date — 100 when there is no date constraint on either side
    or at least 14 days of slack, grading down to 50 for same-day
    availability. A constant 100 here used to inflate every score.

Missing/degenerate data (None names, zero/negative prices) is treated as
"not a match" rather than crashing: the API validates prices as > 0, but
the DB columns carry no CHECK constraint, so a zero price must not turn
GET /api/v1/matches into a 500 (ZeroDivisionError). Reasons describe the
actual component outcomes, not a fixed list.
"""

_FULL_SLACK_DAYS = 14
_MIN_TIME_SCORE = 50.0


def _time_score(demand, product) -> float:
    """Availability-slack score (50-100)."""
    if demand.required_date is None or product.available_until is None:
        return 100.0
    slack = (product.available_until - demand.required_date).days
    if slack >= _FULL_SLACK_DAYS:
        return 100.0
    if slack <= 0:
        return _MIN_TIME_SCORE
    return round(_MIN_TIME_SCORE + (100.0 - _MIN_TIME_SCORE) * slack / _FULL_SLACK_DAYS, 2)


def calculate_match(demand, product):
    # Eligibility checks first: exact product and unit, positive quantities, available stock.
    if not demand.product_name or not product.name:
        return None
    if demand.product_name.strip().lower() != product.name.strip().lower():
        return None
    if not demand.unit or not product.unit:
        return None
    if demand.unit.lower() != product.unit.lower():
        return None
    if product.quantity <= 0 or demand.required_quantity <= 0 or product.status != "available":
        return None
    if not product.price_per_unit or product.price_per_unit <= 0:
        return None
    if not demand.target_price or demand.target_price <= 0:
        return None
    if product.available_until and demand.required_date and product.available_until < demand.required_date:
        return None

    quantity_score = min(product.quantity / demand.required_quantity, 1.0) * 100
    price_score = max(0, min(100, demand.target_price / product.price_per_unit * 100))
    location_score = 100 if (product.district or "").lower() == (demand.district or "").lower() else 40
    time_score = _time_score(demand, product)
    score = 0.30 * 100 + 0.25 * quantity_score + 0.20 * location_score + 0.15 * price_score + 0.10 * time_score
    reasons = ["Product and unit match"]
    if quantity_score >= 100:
        reasons.append("Full quantity available")
    else:
        reasons.append(f"Partial quantity: {quantity_score:.0f}% of required amount in stock")
    if price_score >= 100:
        reasons.append("Price is within buyer budget")
    else:
        reasons.append(f"Price is above buyer budget (price score {price_score:.0f})")
    if location_score == 100:
        reasons.append("Same district")
    else:
        reasons.append("Different district")
    if demand.required_date is None or product.available_until is None:
        reasons.append("No availability-date constraint")
    else:
        slack = (product.available_until - demand.required_date).days
        reasons.append(f"Available {slack} day(s) before the required date")
    return {
        "score": round(score, 2),
        "quantity_score": round(quantity_score, 2),
        "price_score": round(price_score, 2),
        "location_score": location_score,
        "time_score": time_score,
        "reasons": reasons,
    }

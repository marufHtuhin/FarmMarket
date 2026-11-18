import unittest
from types import SimpleNamespace
from app.services.matching import calculate_match

def demand(**overrides):
    values=dict(product_name="Tomato",unit="kg",required_quantity=500,
                target_price=40,district="Gazipur",required_date=None)
    values.update(overrides)
    return SimpleNamespace(**values)

def product(**overrides):
    values=dict(name="Tomato",unit="kg",quantity=600,price_per_unit=35,
                district="Gazipur",status="available",available_until=None)
    values.update(overrides)
    return SimpleNamespace(**values)

class MatchingTests(unittest.TestCase):
    def test_exact_compatible_supply_scores_high(self):
        result=calculate_match(demand(),product())
        self.assertIsNotNone(result)
        self.assertEqual(result["score"],100.0)

    def test_different_product_is_not_matched(self):
        self.assertIsNone(calculate_match(demand(),product(name="Potato")))

    def test_different_unit_is_not_matched(self):
        self.assertIsNone(calculate_match(demand(),product(unit="ton")))

    def test_unavailable_stock_is_not_matched(self):
        self.assertIsNone(calculate_match(demand(),product(quantity=0)))

    def test_removed_product_is_not_matched(self):
        self.assertIsNone(calculate_match(demand(),product(status="removed")))

if __name__=="__main__":
    unittest.main()

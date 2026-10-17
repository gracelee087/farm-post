import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generate import parse_price  # noqa: E402

CASES = {
    "10 kg 12 Euro": ("€12.00", "€1.20/kg"),
    "10 eggs €3": ("€3.00", "€0.30/piece"),
    "500 g €2.50": ("€2.50", "€5.00/kg"),
    "3,50 € for 10 pieces": ("€3.50", "€0.35/piece"),
    "$5 a dozen eggs": ("$5.00", ""),
    "1 dozen $6": ("$6.00", "$0.50/piece"),
    "2 lb honey 9 dollars": ("$9.00", "$4.50/lb"),
    "£4 for 1 l of milk": ("£4.00", "£4.00/l"),
    "5 kg 1,000 KES": ("KES 1000.00", "KES 200.00/kg"),
    "2 kg ₹180": ("₹180.00", "₹90.00/kg"),
    "fresh from the field, 5 kg": ("", ""),
    "12 Euro": ("€12.00", ""),
}


class PriceTest(unittest.TestCase):
    def test_cases(self):
        for note, expected in CASES.items():
            with self.subTest(note=note):
                self.assertEqual(parse_price(note), expected)


if __name__ == "__main__":
    unittest.main()

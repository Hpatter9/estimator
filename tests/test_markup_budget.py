from estimator.config import Company
from estimator.markup import owner_budget


def test_owner_budget_adds_op_then_takes_the_margin():
    assert Company().material_margin_pct == 30.0
    for approved in (5.51, 4.20, 4.92, 0.52, 11.59):
        budget = owner_budget(approved, 30, 20)
        paid = approved * 1.20                           # what the insurer pays for the material with O&P
        assert (paid - budget) / paid >= 0.30 - 1e-9
        assert paid * 0.70 - budget < 0.01               # rounded down by less than a cent
    assert owner_budget(5.51) == 4.62 and owner_budget(4.20) == 3.52 and owner_budget(4.92) == 4.13
    assert owner_budget(10, 0, 0) == 10.0

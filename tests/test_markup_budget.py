from estimator.config import Company
from estimator.markup import owner_budget


def test_owner_budget_keeps_at_least_the_margin():
    assert Company().material_margin_pct == 30.0
    for approved in (5.51, 4.20, 4.92, 0.52, 11.59):
        budget = owner_budget(approved, 30)
        assert (approved - budget) / approved >= 0.30
        assert approved * 0.70 - budget < 0.01          # rounded down by less than a cent
    assert owner_budget(5.51) == 3.85 and owner_budget(4.20) == 2.94 and owner_budget(4.92) == 3.44
    assert owner_budget(10, 0) == 10.0

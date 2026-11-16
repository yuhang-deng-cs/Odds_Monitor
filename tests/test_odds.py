import pytest

from odds import (
    devig_power,
    devig_proportional,
    devig_shin,
    fair_price_table,
    implied_prob,
    overround,
)


def test_worked_example_two_way():
    # 2.00 / 1.80 -> 0.5 + 0.5556 = 1.0556 -> overround 5.56%
    assert overround([2.00, 1.80]) == pytest.approx(0.0556, abs=1e-4)
    fair = devig_proportional([2.00, 1.80])
    assert fair[0] == pytest.approx(0.4737, abs=1e-4)
    assert fair[1] == pytest.approx(0.5263, abs=1e-4)


def test_implied_prob_rejects_invalid_odds():
    with pytest.raises(ValueError):
        implied_prob(1.0)


@pytest.mark.parametrize(
    "odds",
    [[2.00, 1.80], [1.30, 5.50, 9.00], [2.70, 3.30, 2.80], [1.08, 13.0, 34.0], [2.1, 3.6, 3.9]],
)
@pytest.mark.parametrize("method", [devig_proportional, devig_power])
def test_devigged_probs_sum_to_one(odds, method):
    assert sum(method(odds)) == pytest.approx(1.0, abs=1e-9)


def test_power_takes_more_margin_from_longshot():
    odds = [1.30, 5.50, 9.00]  # favourite, mid, longshot
    prop, power = devig_proportional(odds), devig_power(odds)
    assert power[0] > prop[0]  # favourite gets more probability under power
    assert power[2] < prop[2]  # longshot gets less


def test_power_handles_negative_overround():
    # best-of-market prices can sum below 1 (an arb); the method must still return valid probs
    probs = devig_power([2.20, 2.10])
    assert sum(probs) == pytest.approx(1.0, abs=1e-9)
    assert probs[1] > probs[0]


def test_devig_works_for_a_many_runner_race():
    # Synthetic 10-runner horse race (not real data): the maths is not tied to H/D/A.
    race = [3.0, 4.5, 6.0, 8.0, 10.0, 13.0, 17.0, 21.0, 34.0, 51.0]
    assert overround(race) > 0.15  # racing books carry far bigger margins than football
    for devig in (devig_proportional, devig_power):
        p = devig(race)
        assert len(p) == 10 and sum(p) == pytest.approx(1.0)
        assert p == sorted(p, reverse=True)  # shorter price -> higher chance
    # Power de-vig takes relatively more margin off the longshot than off the favourite.
    prop, power = devig_proportional(race), devig_power(race)
    assert power[0] > prop[0] and power[-1] < prop[-1]


def test_fair_price_table_rows():
    rows = fair_price_table([2.0, 1.8])
    assert [r["odds"] for r in rows] == [2.0, 1.8]
    assert rows[0]["implied"] == pytest.approx(0.5)
    assert rows[0]["proportional"] == pytest.approx(0.4737, abs=1e-4)
    assert sum(r["power"] for r in rows) == pytest.approx(1.0)
    assert rows[0]["fair_odds"] == pytest.approx(1 / rows[0]["power"])


def test_shin_two_way_removes_equal_amounts():
    # Known property: with two outcomes Shin takes the same absolute amount off each side.
    # 2.00 / 1.80 -> 0.5 and 0.5556, overround 0.0556 -> 0.5 - 0.0278 and 0.5556 - 0.0278
    p = devig_shin([2.00, 1.80])
    assert p == pytest.approx([0.5 - 0.05556 / 2, 1 / 1.8 - 0.05556 / 2], abs=1e-4)


def test_shin_sums_to_one_and_trims_longshots_most():
    race = [3.0, 4.5, 6.0, 8.0, 10.0, 13.0, 17.0, 21.0, 34.0, 51.0]
    shin, prop = devig_shin(race), devig_proportional(race)
    assert sum(shin) == pytest.approx(1.0)
    assert shin[0] > prop[0] and shin[-1] < prop[-1]  # favourite up, longshot down

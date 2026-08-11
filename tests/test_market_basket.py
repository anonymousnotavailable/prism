"""Tests for modules/market_basket.py — Apriori frequent-itemset mining and
association-rule scoring (support/confidence/lift).
"""
from __future__ import annotations

import random

import pandas as pd
import pytest

from modules import market_basket


def _transactions_df(transactions: list[list[str]]) -> pd.DataFrame:
    """Turn a list of item-lists into a (basket_id, item) long DataFrame."""
    rows = []
    for basket_id, items in enumerate(transactions):
        for item in items:
            rows.append({"basket_id": basket_id, "item": item})
    return pd.DataFrame(rows)


# Classic textbook-style transactions: Milk+Bread co-occur constantly,
# Beer+Diapers co-occur constantly, Eggs is rare and mostly standalone.
_CLASSIC_TRANSACTIONS = (
    [["Milk", "Bread"]] * 30
    + [["Milk", "Bread", "Eggs"]] * 5
    + [["Beer", "Diapers"]] * 20
    + [["Milk"]] * 10
    + [["Bread"]] * 8
    + [["Eggs"]] * 4
)


class TestBuildTransactions:
    def test_groups_items_per_basket(self):
        df = _transactions_df([["A", "B"], ["A", "C"]])
        transactions = market_basket.build_transactions(df, "basket_id", "item")
        assert len(transactions) == 2
        assert frozenset(["A", "B"]) in transactions
        assert frozenset(["A", "C"]) in transactions

    def test_drops_rows_with_missing_basket_or_item(self):
        df = pd.DataFrame(
            {"basket_id": [1, 1, None, 2], "item": ["A", None, "B", "C"]}
        )
        transactions = market_basket.build_transactions(df, "basket_id", "item")
        assert transactions == [frozenset(["A"]), frozenset(["C"])]

    def test_duplicate_items_in_same_basket_collapse(self):
        df = _transactions_df([["A", "A", "B"]])
        transactions = market_basket.build_transactions(df, "basket_id", "item")
        assert transactions == [frozenset(["A", "B"])]

    def test_empty_dataframe_returns_empty_list(self):
        df = pd.DataFrame({"basket_id": [], "item": []})
        assert market_basket.build_transactions(df, "basket_id", "item") == []


class TestFindFrequentItemsets:
    def test_recovers_known_frequent_pair(self):
        transactions = [frozenset(t) for t in _CLASSIC_TRANSACTIONS]
        frequent, n = market_basket.find_frequent_itemsets(transactions, min_support=0.1)
        assert n == len(transactions)
        assert frozenset(["Milk", "Bread"]) in frequent
        milk_bread_support, milk_bread_count = frequent[frozenset(["Milk", "Bread"])]
        assert milk_bread_count == 35  # 30 + 5 baskets contain both
        assert milk_bread_support == pytest.approx(35 / n)

    def test_infrequent_pair_excluded(self):
        transactions = [frozenset(t) for t in _CLASSIC_TRANSACTIONS]
        frequent, _ = market_basket.find_frequent_itemsets(transactions, min_support=0.1)
        # Eggs co-occurs with Milk+Bread in only 5/77 baskets (~6.5%), below a 10% floor.
        assert frozenset(["Milk", "Bread", "Eggs"]) not in frequent

    def test_empty_transactions_returns_empty(self):
        frequent, n = market_basket.find_frequent_itemsets([], min_support=0.1)
        assert frequent == {}
        assert n == 0

    def test_respects_max_itemset_size(self):
        transactions = [frozenset(t) for t in _CLASSIC_TRANSACTIONS]
        frequent, _ = market_basket.find_frequent_itemsets(transactions, min_support=0.01, max_itemset_size=1)
        assert all(len(fs) == 1 for fs in frequent)

    def test_all_singleton_supports_correct(self):
        transactions = [frozenset(["A"]), frozenset(["A", "B"]), frozenset(["B"])]
        frequent, n = market_basket.find_frequent_itemsets(transactions, min_support=0.1)
        assert frequent[frozenset(["A"])] == (2 / 3, 2)
        assert frequent[frozenset(["B"])] == (2 / 3, 2)


class TestComputeAssociationRules:
    def test_finds_expected_rule_with_correct_confidence_and_lift(self):
        df = _transactions_df(_CLASSIC_TRANSACTIONS)
        result = market_basket.compute_association_rules(
            df, "basket_id", "item", min_support=0.1, min_confidence=0.3
        )
        assert "error" not in result
        rules = result["rules"]
        milk_to_bread = rules[(rules["antecedent"] == "Milk") & (rules["consequent"] == "Bread")]
        assert len(milk_to_bread) == 1
        row = milk_to_bread.iloc[0]
        # Milk appears in 30+5+10 = 45 baskets; Milk & Bread together in 35.
        assert row["confidence"] == pytest.approx(35 / 45, abs=1e-3)
        assert row["support"] == pytest.approx(35 / 77, abs=1e-3)

    def test_beer_diapers_rule_present_with_high_lift(self):
        df = _transactions_df(_CLASSIC_TRANSACTIONS)
        result = market_basket.compute_association_rules(
            df, "basket_id", "item", min_support=0.1, min_confidence=0.3
        )
        rules = result["rules"]
        beer_diapers = rules[(rules["antecedent"] == "Beer") & (rules["consequent"] == "Diapers")]
        assert len(beer_diapers) == 1
        assert beer_diapers.iloc[0]["confidence"] == pytest.approx(1.0)
        assert beer_diapers.iloc[0]["lift"] > 1.0

    def test_rules_sorted_by_lift_descending(self):
        df = _transactions_df(_CLASSIC_TRANSACTIONS)
        result = market_basket.compute_association_rules(
            df, "basket_id", "item", min_support=0.05, min_confidence=0.1
        )
        lifts = result["rules"]["lift"].tolist()
        assert lifts == sorted(lifts, reverse=True)

    def test_same_column_twice_is_error(self):
        df = _transactions_df(_CLASSIC_TRANSACTIONS)
        result = market_basket.compute_association_rules(df, "basket_id", "basket_id")
        assert "error" in result

    def test_too_few_baskets_is_error(self):
        df = _transactions_df([["A", "B"]] * 3)
        result = market_basket.compute_association_rules(df, "basket_id", "item")
        assert "error" in result

    def test_all_missing_data_is_error(self):
        df = pd.DataFrame({"basket_id": [None, None], "item": [None, None]})
        result = market_basket.compute_association_rules(df, "basket_id", "item")
        assert "error" in result

    def test_unreachable_support_threshold_is_error(self):
        df = _transactions_df(_CLASSIC_TRANSACTIONS)
        result = market_basket.compute_association_rules(df, "basket_id", "item", min_support=0.99)
        assert "error" in result

    def test_no_qualifying_pairs_yields_empty_rules_not_error(self):
        df = _transactions_df(_CLASSIC_TRANSACTIONS)
        # At 0.5 support only the two singleton items (Milk, Bread) clear
        # the bar — no size->=2 itemset survives, so there's nothing to
        # build a rule from, but the frequent-itemsets table is non-empty
        # and this is NOT an error (distinct from the "no itemsets at all"
        # case tested by test_unreachable_support_threshold_is_error).
        result = market_basket.compute_association_rules(
            df, "basket_id", "item", min_support=0.5, min_confidence=0.1
        )
        assert "error" not in result
        assert result["rules"].empty
        assert not result["frequent_itemsets"].empty
        assert all(size == 1 for size in result["frequent_itemsets"]["size"])

    def test_confidence_filter_excludes_lower_confidence_rule(self):
        df = _transactions_df(_CLASSIC_TRANSACTIONS)
        # Milk -> Bread confidence is ~0.78; Beer -> Diapers is 1.0. A
        # 0.9 floor should keep the perfect rule and drop the imperfect one.
        result = market_basket.compute_association_rules(
            df, "basket_id", "item", min_support=0.1, min_confidence=0.9
        )
        rules = result["rules"]
        assert ((rules["antecedent"] == "Beer") & (rules["consequent"] == "Diapers")).any()
        assert not ((rules["antecedent"] == "Milk") & (rules["consequent"] == "Bread")).any()

    def test_reports_basket_and_item_counts(self):
        df = _transactions_df(_CLASSIC_TRANSACTIONS)
        result = market_basket.compute_association_rules(df, "basket_id", "item", min_support=0.1)
        assert result["n_baskets_total"] == len(_CLASSIC_TRANSACTIONS)
        assert result["n_baskets"] == len(_CLASSIC_TRANSACTIONS)
        assert result["n_distinct_items"] == 5  # Milk, Bread, Eggs, Beer, Diapers
        assert result["sampled"] is False

    def test_samples_when_over_max_baskets(self):
        rng = random.Random(0)
        transactions = [["Milk", "Bread"] if rng.random() < 0.5 else ["Beer", "Diapers"] for _ in range(200)]
        df = _transactions_df(transactions)
        result = market_basket.compute_association_rules(
            df, "basket_id", "item", min_support=0.05, max_baskets=50
        )
        assert "error" not in result
        assert result["sampled"] is True
        assert result["n_baskets"] == 50
        assert result["n_baskets_total"] == 200

    def test_caps_distinct_items_for_tractability(self):
        # 250 baskets, each with one of 250 distinct rare items plus a
        # shared "Common" item — only the top max_distinct_items items
        # (by frequency) should survive past the singleton level.
        transactions = [["Common", f"Rare{i}"] for i in range(250)]
        df = _transactions_df(transactions)
        result = market_basket.compute_association_rules(
            df, "basket_id", "item", min_support=0.001, max_distinct_items=50
        )
        assert "error" not in result
        # "Common" appears in every basket so it always survives the cap.
        assert "Common" in result["frequent_itemsets"]["itemset"].str.cat(sep=", ")


class TestRuleVerdict:
    @pytest.mark.parametrize(
        "lift,expected_fragment",
        [(4.0, "very strong"), (2.0, "meaningfully"), (1.2, "slightly"), (1.0, "no association"), (0.5, "less")],
    )
    def test_verdict_matches_lift_band(self, lift, expected_fragment):
        verdict = market_basket.rule_verdict(lift)
        assert expected_fragment in verdict.lower()


class TestBuildRulesChart:
    def test_builds_figure_for_populated_rules(self):
        df = _transactions_df(_CLASSIC_TRANSACTIONS)
        result = market_basket.compute_association_rules(df, "basket_id", "item", min_support=0.1)
        fig = market_basket.build_rules_chart(result["rules"])
        assert fig is not None

    def test_builds_figure_for_empty_rules(self):
        empty = pd.DataFrame(columns=["antecedent", "consequent", "support", "confidence", "lift", "count"])
        fig = market_basket.build_rules_chart(empty)
        assert fig is not None

"""Cross-validation test for backtest.py FBAMM simulation."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from backtest import simulate_fbamm_block, constant_product_out


def test_single_buyer():
    """Single buyer, no seller. All goes through AMM."""
    r0 = 1000 * 10**18  # 1000 token0
    r1 = 1000 * 10**18  # 1000 token1

    swaps = [{"amount0In": "0", "amount1In": str(10 * 10**18), "amount0Out": "0", "amount1Out": "0"}]

    result = simulate_fbamm_block(r0, r1, swaps)

    fee = (10 * 10**18 * 30) // 10000
    net = 10 * 10**18 - fee
    expected_out = (net * r0) // (r1 + net)

    assert result is not None
    assert result["Qb"] == net, f"Qb mismatch: {result['Qb']} != {net}"
    assert result["Qs"] == 0
    assert result["netting_ratio"] == 0.0
    assert result["total_token0_for_buyers"] == expected_out, f"Output mismatch: {result['total_token0_for_buyers']} != {expected_out}"
    print(f"  Single buyer: OK (output={expected_out})")


def test_balanced():
    """Equal buy and sell. Pure netting, no AMM."""
    r0 = 1000 * 10**18
    r1 = 1000 * 10**18

    swaps = [
        {"amount0In": "0", "amount1In": str(10 * 10**18), "amount0Out": "0", "amount1Out": "0"},  # buy
        {"amount0In": str(10 * 10**18), "amount1In": "0", "amount0Out": "0", "amount1Out": "0"},  # sell
    ]

    result = simulate_fbamm_block(r0, r1, swaps)

    fee = (10 * 10**18 * 30) // 10000
    net = 10 * 10**18 - fee

    assert result is not None
    assert result["Qb"] == net
    assert result["Qs"] == net
    assert result["netting_ratio"] == 1.0, f"Should be fully netted: {result['netting_ratio']}"
    assert result["amount_out_from_amm"] == 0, "No AMM interaction for balanced batch"
    # Buyers get all of Qs (sellers' token0)
    assert result["total_token0_for_buyers"] == net
    # Sellers get all of Qb equivalent (buyers' token1)
    assert result["total_token1_for_sellers"] == net
    print(f"  Balanced: OK (netting_ratio=1.0, no AMM)")


def test_unbalanced_buy_heavy():
    """More buying than selling. Partial netting + AMM."""
    r0 = 1000 * 10**18
    r1 = 1000 * 10**18

    buy_amount = 20 * 10**18
    sell_amount = 10 * 10**18

    swaps = [
        {"amount0In": "0", "amount1In": str(buy_amount), "amount0Out": "0", "amount1Out": "0"},
        {"amount0In": str(sell_amount), "amount1In": "0", "amount0Out": "0", "amount1Out": "0"},
    ]

    result = simulate_fbamm_block(r0, r1, swaps)

    buy_fee = (buy_amount * 30) // 10000
    sell_fee = (sell_amount * 30) // 10000
    net_buy = buy_amount - buy_fee
    net_sell = sell_amount - sell_fee

    net_demand = net_buy - net_sell
    amm_out = (net_demand * r0) // (r1 + net_demand)

    assert result is not None
    assert result["Qb"] == net_buy
    assert result["Qs"] == net_sell
    assert 0 < result["netting_ratio"] < 1
    assert result["amount_out_from_amm"] == amm_out
    assert result["total_token0_for_buyers"] == net_sell + amm_out
    assert result["total_token1_for_sellers"] == net_sell  # sellers get matched portion
    print(f"  Unbalanced buy-heavy: OK (netting={result['netting_ratio']:.2%}, amm_out={amm_out})")


def test_constant_product():
    """Verify constant product formula."""
    assert constant_product_out(10, 100, 200) == (10 * 200) // (100 + 10)  # 18
    assert constant_product_out(0, 100, 200) == 0
    assert constant_product_out(100, 100, 100) == 50  # half the reserve
    print("  Constant product: OK")


if __name__ == "__main__":
    print("Running backtest cross-validation tests...")
    test_constant_product()
    test_single_buyer()
    test_balanced()
    test_unbalanced_buy_heavy()
    print("\nAll tests passed!")

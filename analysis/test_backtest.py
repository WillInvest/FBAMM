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

    # With cross-decimal netting: matched_token1 = (Qs * r1) / r0 = Qs (when r0 == r1)
    matched_token1 = (net_sell * r1) // r0  # = net_sell when r0 == r1
    net_demand = net_buy - matched_token1
    amm_out = (net_demand * r0) // (r1 + net_demand)

    assert result is not None
    assert result["Qb"] == net_buy
    assert result["Qs"] == net_sell
    assert 0 < result["netting_ratio"] < 1
    assert result["amount_out_from_amm"] == amm_out
    assert result["total_token0_for_buyers"] == net_sell + amm_out
    assert result["total_token1_for_sellers"] == matched_token1
    print(f"  Unbalanced buy-heavy: OK (netting={result['netting_ratio']:.2%}, amm_out={amm_out})")


def test_cross_decimal():
    """Test with different decimals: WETH (18) vs USDC (6)."""
    # 1000 WETH, 2M USDC → spot price = 2000 USDC/WETH
    r0 = 1000 * 10**18       # 1000 WETH
    r1 = 2_000_000 * 10**6   # 2M USDC

    # Buyer: buy ETH with 4000 USDC
    # Seller: sell 1 ETH
    swaps = [
        {"amount0In": "0", "amount1In": str(4000 * 10**6), "amount0Out": "0", "amount1Out": "0"},
        {"amount0In": str(1 * 10**18), "amount1In": "0", "amount0Out": "0", "amount1Out": "0"},
    ]

    result = simulate_fbamm_block(r0, r1, swaps)

    buy_fee = (4000 * 10**6 * 30) // 10000
    sell_fee = (1 * 10**18 * 30) // 10000
    net_buy = 4000 * 10**6 - buy_fee    # ~3988e6 USDC
    net_sell = 1 * 10**18 - sell_fee     # ~0.997e18 WETH

    assert result is not None

    # Buy excess: net_buy * r0 vs net_sell * r1
    # 3988e6 * 1000e18 vs 997e15 * 2e9 → compare economic values
    buy_value = net_buy * r0
    sell_value = net_sell * r1
    assert buy_value > sell_value, "Should be buy excess (4000 USDC > 1 ETH at 2000)"

    # matched_token1 = (Qs * r1) / r0 = (net_sell * 2e9) / 1e18 * 1e6 ≈ 1994 USDC
    matched = (net_sell * r1) // r0
    assert matched > 0, f"Matched should be > 0: {matched}"

    # Seller should get ~1994 USDC (spot value of 1 ETH minus fee)
    assert result["total_token1_for_sellers"] == matched
    assert result["total_token0_for_buyers"] > 0

    # Netting ratio should be meaningful (not 0 or near 0)
    assert result["netting_ratio"] > 0.3, f"Netting ratio too low: {result['netting_ratio']}"

    print(f"  Cross-decimal: OK (netting={result['netting_ratio']:.2%}, seller_gets={matched} USDC, buyer_gets={result['total_token0_for_buyers']} WETH)")


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
    test_cross_decimal()
    print("\nAll tests passed!")

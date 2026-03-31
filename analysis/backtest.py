"""Per-block isolated FBAMM backtest orchestrator.

For each block in the swap data:
1. Read Uniswap V2 reserves and swap events (from pre-fetched JSON)
2. Simulate FBAMM clearing with matching reserves
3. Compare execution quality metrics
"""

import json
import math
import os
import sys


def constant_product_out(amount_in, reserve_in, reserve_out):
    """Calculate output amount using constant product formula."""
    return (amount_in * reserve_out) // (reserve_in + amount_in)


def simulate_fbamm_block(reserve0, reserve1, swaps):
    """Simulate FBAMM clearing for one block.

    Args:
        reserve0, reserve1: initial reserves (matching Uniswap V2)
        swaps: list of swap dicts with amount0In, amount1In, amount0Out, amount1Out

    Returns:
        dict with FBAMM metrics
    """
    FEE_BPS = 30
    LP_FEE_SHARE = 80

    Qb = 0  # token1 deposited to buy token0
    Qs = 0  # token0 deposited to buy token1
    pending_fees0 = 0
    pending_fees1 = 0

    buy_orders = {}  # address -> amount
    sell_orders = {}  # address -> amount

    for i, swap in enumerate(swaps):
        a0in = int(swap["amount0In"])
        a1in = int(swap["amount1In"])

        trader = f"trader_{i}"

        if a1in > 0:
            # Buying token0 with token1
            fee = (a1in * FEE_BPS) // 10000
            net = a1in - fee
            pending_fees1 += fee
            Qb += net
            buy_orders[trader] = buy_orders.get(trader, 0) + net
        elif a0in > 0:
            # Selling token0 for token1
            fee = (a0in * FEE_BPS) // 10000
            net = a0in - fee
            pending_fees0 += fee
            Qs += net
            sell_orders[trader] = sell_orders.get(trader, 0) + net

    if Qb == 0 and Qs == 0:
        return None

    # Clearing
    amount_out = 0
    r0, r1 = reserve0, reserve1

    if Qb > Qs:
        net_demand = Qb - Qs
        amount_out = (net_demand * r0) // (r1 + net_demand)
        r1 += net_demand
        r0 -= amount_out
    elif Qs > Qb:
        net_demand = Qs - Qb
        amount_out = (net_demand * r1) // (r0 + net_demand)
        r0 += net_demand
        r1 -= amount_out

    # Distribution totals
    if Qb >= Qs:
        total_token0_for_buyers = Qs + amount_out
        total_token1_for_sellers = Qs  # matched from buyers
    else:
        total_token0_for_buyers = Qb  # matched from sellers
        total_token1_for_sellers = Qb + amount_out

    # Unified prices (what each side gets per unit deposited)
    buyer_price = total_token0_for_buyers / Qb if Qb > 0 else 0  # token0 per token1
    seller_price = total_token1_for_sellers / Qs if Qs > 0 else 0  # token1 per token0

    # Fee distribution
    lp_fee0 = (pending_fees0 * LP_FEE_SHARE) // 100
    lp_fee1 = (pending_fees1 * LP_FEE_SHARE) // 100
    r0 += lp_fee0
    r1 += lp_fee1

    # Netting ratio
    netted = min(Qb, Qs)
    total = max(Qb, Qs)
    netting_ratio = netted / total if total > 0 else 0

    return {
        "Qb": Qb,
        "Qs": Qs,
        "netting_ratio": netting_ratio,
        "amount_out_from_amm": amount_out,
        "reserve0_after": r0,
        "reserve1_after": r1,
        "buyer_price": buyer_price,
        "seller_price": seller_price,
        "total_token0_for_buyers": total_token0_for_buyers,
        "total_token1_for_sellers": total_token1_for_sellers,
        "pending_fees0": pending_fees0,
        "pending_fees1": pending_fees1,
        "num_buyers": len(buy_orders),
        "num_sellers": len(sell_orders),
    }


def analyze_univ2_block(reserve0, reserve1, swaps):
    """Analyze actual Uniswap V2 execution for one block.

    Returns metrics about per-trade prices and variance.
    """
    prices = []
    r0, r1 = reserve0, reserve1

    for swap in swaps:
        a0in = int(swap["amount0In"])
        a1in = int(swap["amount1In"])
        a0out = int(swap["amount0Out"])
        a1out = int(swap["amount1Out"])

        if a1in > 0 and a0out > 0:
            # Buying token0 with token1
            price = a1in / a0out  # token1 per token0
            prices.append({"direction": "buy", "amountIn": a1in, "amountOut": a0out, "price": price})
            r1 += a1in
            r0 -= a0out
        elif a0in > 0 and a1out > 0:
            # Selling token0 for token1
            price = a1out / a0in  # token1 per token0 (inverse for comparison)
            prices.append({"direction": "sell", "amountIn": a0in, "amountOut": a1out, "price": price})
            r0 += a0in
            r1 -= a1out

    if not prices:
        return None

    all_prices = [p["price"] for p in prices]
    avg_price = sum(all_prices) / len(all_prices)

    if len(all_prices) > 1:
        variance = sum((p - avg_price) ** 2 for p in all_prices) / (len(all_prices) - 1)
    else:
        variance = 0

    return {
        "num_trades": len(prices),
        "prices": all_prices,
        "avg_price": avg_price,
        "price_variance": variance,
        "min_price": min(all_prices),
        "max_price": max(all_prices),
        "reserve0_after": r0,
        "reserve1_after": r1,
    }


def main():
    data_file = sys.argv[1] if len(sys.argv) > 1 else "data/ETH_USDC_19000000_19000100.json"

    if not os.path.exists(data_file):
        print(f"Data file not found: {data_file}", file=sys.stderr)
        print("Run fetch_swaps.py first to fetch swap data.", file=sys.stderr)
        sys.exit(1)

    with open(data_file) as f:
        data = json.load(f)

    results = []

    for block_data in data["blocks"]:
        block_num = block_data["blockNumber"]
        r0 = int(block_data["reserve0"])
        r1 = int(block_data["reserve1"])
        swaps = block_data["swaps"]

        if not swaps:
            continue

        univ2 = analyze_univ2_block(r0, r1, swaps)
        fbamm = simulate_fbamm_block(r0, r1, swaps)

        if univ2 is None or fbamm is None:
            continue

        results.append({
            "blockNumber": block_num,
            "reserve0": str(r0),
            "reserve1": str(r1),
            "numSwaps": len(swaps),
            "univ2": {
                "num_trades": univ2["num_trades"],
                "avg_price": univ2["avg_price"],
                "price_variance": univ2["price_variance"],
                "min_price": univ2["min_price"],
                "max_price": univ2["max_price"],
            },
            "fbamm": {
                "netting_ratio": fbamm["netting_ratio"],
                "buyer_price": fbamm["buyer_price"],
                "seller_price": fbamm["seller_price"],
                "num_buyers": fbamm["num_buyers"],
                "num_sellers": fbamm["num_sellers"],
                "Qb": fbamm["Qb"],
                "Qs": fbamm["Qs"],
                "amount_out_from_amm": fbamm["amount_out_from_amm"],
            },
        })

    out_path = data_file.replace(".json", "_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Processed {len(results)} blocks, saved to {out_path}")


if __name__ == "__main__":
    main()

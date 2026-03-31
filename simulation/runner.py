"""Simulation runner: feeds the same ZI trader stream to both UniV2 and FBAMM pools.

The key methodological point: BOTH pools start with identical reserves and
receive the SAME sequence of trader orders. The only difference is the
execution mechanism (sequential vs batch clearing).
"""

import json
import os
import statistics
from pools import UniswapV2Pool, FBAMMPool
from agents import TraderPopulation


def run_simulation(
    num_blocks: int = 1000,
    reserve0: int = 1000 * 10**18,       # 1000 ETH
    reserve1: int = 2_000_000 * 10**6,   # 2M USDC (6 decimals)
    arrival_rate: float = 5.0,            # avg 5 traders per block
    buy_prob: float = 0.5,               # balanced market
    mean_size_token0: float = 1.0,        # mean 1 ETH per trade
    size_std_token0: float = 0.8,
    fee_bps: int = 30,
    seed: int = 42,
) -> dict:
    """Run a paired simulation: same traders → UniV2 and FBAMM.

    Sizes are in token0 units (ETH). For buy orders, we convert to token1
    (USDC) at the current UniV2 spot price to keep economic intent identical.
    """
    # Create identical pools
    univ2 = UniswapV2Pool(reserve0, reserve1, fee_bps)
    fbamm = FBAMMPool(reserve0, reserve1, fee_bps)

    # Create trader population
    pop = TraderPopulation(
        num_traders=200,
        arrival_rate=arrival_rate,
        buy_prob=buy_prob,
        mean_size=mean_size_token0,
        size_std=size_std_token0,
        seed=seed,
    )

    # Per-block metrics
    block_metrics = []

    for block in range(num_blocks):
        orders = pop.generate_block_orders(block)

        if not orders:
            continue

        # Track UniV2 per-trade prices this block
        univ2_prices_buy = []
        univ2_prices_sell = []

        for trader_id, is_buy, size_eth in orders:
            if is_buy:
                # Convert ETH amount to USDC at current UniV2 spot
                # spot_raw = reserve1 / reserve0 (raw units, different decimals)
                # amount_usdc_raw = size_eth * 10^18 * reserve1 / reserve0
                amount_in_usdc = int(size_eth * 10**18 * univ2.reserve1 // univ2.reserve0)
                if amount_in_usdc <= 0:
                    continue

                # UniV2: execute immediately
                out = univ2.swap(block, True, amount_in_usdc)
                if out > 0:
                    # Price in human-readable USDC per ETH
                    price = (amount_in_usdc / 10**6) / (out / 10**18)
                    univ2_prices_buy.append(price)

                # FBAMM: queue
                fbamm.swap(trader_id, True, amount_in_usdc)
            else:
                amount_in_eth = int(size_eth * 10**18)
                if amount_in_eth <= 0:
                    continue

                # UniV2: execute immediately
                out = univ2.swap(block, False, amount_in_eth)
                if out > 0:
                    # Price in human-readable USDC per ETH
                    price = (out / 10**6) / (amount_in_eth / 10**18)
                    univ2_prices_sell.append(price)

                # FBAMM: queue
                fbamm.swap(trader_id, False, amount_in_eth)

        # FBAMM: clear the batch
        clear_result = fbamm.clear(block)

        # Compute block metrics
        all_univ2_prices = univ2_prices_buy + univ2_prices_sell
        if len(all_univ2_prices) >= 2:
            price_var = statistics.variance(all_univ2_prices)
        elif len(all_univ2_prices) == 1:
            price_var = 0
        else:
            price_var = None

        bm = {
            "block": block,
            "num_orders": len(orders),
            "univ2_num_trades": len(all_univ2_prices),
            "univ2_price_variance": price_var,
            "univ2_spot_price": univ2.spot_price(),
            "fbamm_spot_price": fbamm.spot_price(),
        }

        if all_univ2_prices:
            bm["univ2_avg_price"] = statistics.mean(all_univ2_prices)
            bm["univ2_min_price"] = min(all_univ2_prices)
            bm["univ2_max_price"] = max(all_univ2_prices)
            bm["univ2_spread"] = max(all_univ2_prices) - min(all_univ2_prices)

        if clear_result:
            bm["fbamm_netting_ratio"] = clear_result["netting_ratio"]
            bm["fbamm_num_buyers"] = clear_result["num_buyers"]
            bm["fbamm_num_sellers"] = clear_result["num_sellers"]

        block_metrics.append(bm)

    # Aggregate results
    return _aggregate(univ2, fbamm, block_metrics, num_blocks)


def _aggregate(univ2, fbamm, block_metrics, num_blocks) -> dict:
    """Compute summary statistics."""

    # Filter blocks with trades
    traded_blocks = [b for b in block_metrics if b.get("univ2_num_trades", 0) > 0]
    multi_trade_blocks = [b for b in traded_blocks if b["univ2_num_trades"] >= 2]
    netting_blocks = [b for b in block_metrics if b.get("fbamm_netting_ratio") is not None]

    # UniV2 price variance
    variances = [b["univ2_price_variance"] for b in multi_trade_blocks
                 if b["univ2_price_variance"] is not None and b["univ2_price_variance"] > 0]

    # UniV2 spreads
    spreads = [b["univ2_spread"] for b in multi_trade_blocks if "univ2_spread" in b]

    # FBAMM netting
    netting_ratios = [b["fbamm_netting_ratio"] for b in netting_blocks]
    both_sides = [b for b in netting_blocks
                  if b.get("fbamm_num_buyers", 0) > 0 and b.get("fbamm_num_sellers", 0) > 0]

    result = {
        "config": {
            "num_blocks": num_blocks,
            "initial_reserve0": str(univ2.reserve0),
            "initial_reserve1": str(univ2.reserve1),
        },
        "summary": {
            "total_blocks_with_trades": len(traded_blocks),
            "multi_trade_blocks": len(multi_trade_blocks),
            "avg_trades_per_block": (statistics.mean([b["univ2_num_trades"] for b in traded_blocks])
                                     if traded_blocks else 0),
        },
        "execution_quality": {
            "univ2_avg_within_block_price_variance": (
                statistics.mean(variances) if variances else 0),
            "univ2_max_within_block_price_variance": max(variances) if variances else 0,
            "fbamm_within_block_price_variance": 0,  # by design
            "univ2_avg_spread_per_block": (
                statistics.mean(spreads) if spreads else 0),
            "univ2_max_spread_per_block": max(spreads) if spreads else 0,
            "fbamm_spread_per_block": 0,  # unified price
        },
        "netting": {
            "avg_netting_ratio": (statistics.mean(netting_ratios) if netting_ratios else 0),
            "max_netting_ratio": max(netting_ratios) if netting_ratios else 0,
            "blocks_with_both_sides": len(both_sides),
            "blocks_with_both_sides_pct": (
                len(both_sides) / len(netting_blocks) * 100 if netting_blocks else 0),
        },
        "pool_state": {
            "univ2_final_reserve0": str(univ2.reserve0),
            "univ2_final_reserve1": str(univ2.reserve1),
            "univ2_final_k": str(univ2.k()),
            "fbamm_final_reserve0": str(fbamm.reserve0),
            "fbamm_final_reserve1": str(fbamm.reserve1),
            "fbamm_final_k": str(fbamm.k()),
        },
        "lp_returns": {
            "univ2_total_fees0": str(univ2.total_fees0),
            "univ2_total_fees1": str(univ2.total_fees1),
            "fbamm_total_lp_fees0": str(fbamm.total_lp_fees0),
            "fbamm_total_lp_fees1": str(fbamm.total_lp_fees1),
            "fbamm_total_clearer_fees0": str(fbamm.total_clearer_fees0),
            "fbamm_total_clearer_fees1": str(fbamm.total_clearer_fees1),
        },
        "block_metrics": block_metrics,
    }

    return result


def print_summary(results: dict):
    """Print human-readable summary."""
    s = results["summary"]
    eq = results["execution_quality"]
    n = results["netting"]
    lp = results["lp_returns"]

    print("=" * 60)
    print("FBAMM vs UniswapV2 — ZI Trader Simulation")
    print("=" * 60)
    print(f"Blocks simulated: {results['config']['num_blocks']}")
    print(f"Blocks with trades: {s['total_blocks_with_trades']}")
    print(f"Multi-trade blocks: {s['multi_trade_blocks']}")
    print(f"Avg trades per block: {s['avg_trades_per_block']:.1f}")
    print()
    print("--- Execution Quality ---")
    print(f"UniV2 avg within-block price variance: {eq['univ2_avg_within_block_price_variance']:.4f}")
    print(f"UniV2 max within-block price variance: {eq['univ2_max_within_block_price_variance']:.4f}")
    print(f"FBAMM within-block price variance: {eq['fbamm_within_block_price_variance']} (unified price)")
    print(f"UniV2 avg price spread per block: ${eq['univ2_avg_spread_per_block']:.2f}")
    print(f"UniV2 max price spread per block: ${eq['univ2_max_spread_per_block']:.2f}")
    print(f"FBAMM price spread per block: $0.00 (unified price)")
    print()
    print("--- Netting Efficiency ---")
    print(f"Avg netting ratio: {n['avg_netting_ratio']:.2%}")
    print(f"Max netting ratio: {n['max_netting_ratio']:.2%}")
    print(f"Blocks with both-side trades: {n['blocks_with_both_sides']}/{s['total_blocks_with_trades']} ({n['blocks_with_both_sides_pct']:.1f}%)")
    print()
    print("--- LP Returns ---")
    print(f"UniV2 fees (token0): {int(lp['univ2_total_fees0']) / 10**18:.4f} ETH")
    print(f"UniV2 fees (token1): {int(lp['univ2_total_fees1']) / 10**6:.2f} USDC")
    print(f"FBAMM LP fees (token0): {int(lp['fbamm_total_lp_fees0']) / 10**18:.4f} ETH")
    print(f"FBAMM LP fees (token1): {int(lp['fbamm_total_lp_fees1']) / 10**6:.2f} USDC")
    print(f"FBAMM clearer fees (token0): {int(lp['fbamm_total_clearer_fees0']) / 10**18:.4f} ETH")
    print(f"FBAMM clearer fees (token1): {int(lp['fbamm_total_clearer_fees1']) / 10**6:.2f} USDC")
    print()
    print("--- Pool State ---")
    print(f"UniV2 reserves: {int(results['pool_state']['univ2_final_reserve0']) / 10**18:.2f} ETH / {int(results['pool_state']['univ2_final_reserve1']) / 10**6:.2f} USDC")
    print(f"FBAMM reserves: {int(results['pool_state']['fbamm_final_reserve0']) / 10**18:.2f} ETH / {int(results['pool_state']['fbamm_final_reserve1']) / 10**6:.2f} USDC")


if __name__ == "__main__":
    import sys

    num_blocks = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    arrival_rate = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42

    print(f"Running simulation: {num_blocks} blocks, λ={arrival_rate} traders/block, seed={seed}")
    print()

    results = run_simulation(
        num_blocks=num_blocks,
        arrival_rate=arrival_rate,
        seed=seed,
    )

    print_summary(results)

    # Save full results
    os.makedirs("data", exist_ok=True)
    out_path = f"data/zi_sim_{num_blocks}blocks_lambda{arrival_rate}_seed{seed}.json"

    # Strip block_metrics for JSON (too large)
    save_results = {k: v for k, v in results.items() if k != "block_metrics"}
    with open(out_path, "w") as f:
        json.dump(save_results, f, indent=2)
    print(f"\nSaved to {out_path}")

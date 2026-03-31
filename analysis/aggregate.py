"""Aggregate backtest results into comparison metrics."""

import json
import statistics
import sys


def main():
    results_file = sys.argv[1] if len(sys.argv) > 1 else "data/ETH_USDC_19000000_19000100_results.json"

    with open(results_file) as f:
        results = json.load(f)

    if not results:
        print("No results to analyze.")
        return

    # Execution quality metrics
    price_variances = [b["univ2"]["price_variance"] for b in results if b["univ2"]["price_variance"] > 0]
    netting_ratios = [b["fbamm"]["netting_ratio"] for b in results]
    num_swaps = [b["numSwaps"] for b in results]

    print(f"=== FBAMM vs Uniswap V2 Comparison ===")
    print(f"Blocks analyzed: {len(results)}")
    print(f"Total swaps: {sum(num_swaps)}")
    print(f"Avg swaps per block: {statistics.mean(num_swaps):.1f}")
    print()

    print("--- Execution Quality ---")
    if price_variances:
        print(f"UniV2 avg within-block price variance: {statistics.mean(price_variances):.6e}")
        print(f"UniV2 max within-block price variance: {max(price_variances):.6e}")
    print(f"FBAMM within-block price variance: 0 (unified price by design)")
    print()

    print("--- Netting Efficiency ---")
    print(f"Avg netting ratio: {statistics.mean(netting_ratios):.2%}")
    if netting_ratios:
        print(f"Min netting ratio: {min(netting_ratios):.2%}")
        print(f"Max netting ratio: {max(netting_ratios):.2%}")

    # Blocks with full netting (no AMM interaction needed)
    full_netting = sum(1 for r in netting_ratios if r >= 0.99)
    print(f"Blocks with near-full netting: {full_netting}/{len(results)} ({full_netting/len(results)*100:.1f}%)")
    print()

    print("--- Reserve Impact ---")
    one_sided = sum(1 for b in results if b["fbamm"]["num_buyers"] == 0 or b["fbamm"]["num_sellers"] == 0)
    print(f"One-sided blocks (no netting possible): {one_sided}/{len(results)} ({one_sided/len(results)*100:.1f}%)")


if __name__ == "__main__":
    main()

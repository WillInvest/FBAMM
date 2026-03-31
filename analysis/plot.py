"""Generate comparison plots from backtest results."""

import json
import os
import sys

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    print("Install matplotlib: pip install matplotlib", file=sys.stderr)
    sys.exit(1)


def main():
    results_file = sys.argv[1] if len(sys.argv) > 1 else "data/ETH_USDC_19000000_19000100_results.json"

    with open(results_file) as f:
        results = json.load(f)

    output_dir = "data/plots"
    os.makedirs(output_dir, exist_ok=True)

    # Plot 1: Swaps per block
    swaps_per_block = [b["numSwaps"] for b in results]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(swaps_per_block, bins=30, edgecolor="black", alpha=0.7)
    ax.set_xlabel("Swaps per Block")
    ax.set_ylabel("Frequency")
    ax.set_title("Distribution of Swap Count per Block (Uniswap V2)")
    fig.savefig(f"{output_dir}/swaps_per_block.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_dir}/swaps_per_block.png")

    # Plot 2: Within-block price variance
    variances = [b["univ2"]["price_variance"] for b in results if b["univ2"]["price_variance"] > 0]
    if variances:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.hist(variances, bins=30, edgecolor="black", alpha=0.7, label="Uniswap V2")
        ax.axvline(x=0, color="red", linestyle="--", linewidth=2, label="FBAMM (zero by design)")
        ax.set_xlabel("Within-Block Price Variance")
        ax.set_ylabel("Frequency")
        ax.set_title("Price Variance per Block: Uniswap V2 vs FBAMM")
        ax.legend()
        fig.savefig(f"{output_dir}/price_variance.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Saved {output_dir}/price_variance.png")

    # Plot 3: Netting ratio distribution
    netting_ratios = [b["fbamm"]["netting_ratio"] for b in results]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(netting_ratios, bins=20, edgecolor="black", alpha=0.7, color="green")
    ax.set_xlabel("Netting Ratio (min(Qb,Qs) / max(Qb,Qs))")
    ax.set_ylabel("Frequency")
    ax.set_title("FBAMM Netting Efficiency per Block")
    ax.axvline(x=sum(netting_ratios)/len(netting_ratios), color="red", linestyle="--", label=f"Mean: {sum(netting_ratios)/len(netting_ratios):.2%}")
    ax.legend()
    fig.savefig(f"{output_dir}/netting_ratio.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_dir}/netting_ratio.png")

    # Plot 4: Netting ratio vs swaps per block
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(swaps_per_block, netting_ratios, alpha=0.5, s=20)
    ax.set_xlabel("Swaps per Block")
    ax.set_ylabel("Netting Ratio")
    ax.set_title("Netting Efficiency vs Block Activity")
    fig.savefig(f"{output_dir}/netting_vs_activity.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_dir}/netting_vs_activity.png")


if __name__ == "__main__":
    main()

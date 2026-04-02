"""Sensitivity analysis: sweep sigma (volatility) and lambda (arrival rate).

For each (sigma, lambda) pair, runs 5 independent seeds and reports:
  - FBAMM vs UniV2 arb profit (ratio and absolute)
  - FBAMM vs UniV2 LP net PnL
  - FBAMM avg netting ratio
  - FBAMM LP fees vs UniV2 LP fees

Key question: When (if ever) is FBAMM better for LPs than UniV2?
"""

import json
import os
import statistics
from runner import run_simulation

# Parameter grid
SIGMAS       = [0.005, 0.01, 0.02, 0.04, 0.08]   # per-block volatility
LAMBDAS      = [1, 3, 5, 10, 20]                   # avg ZI traders / block
SEEDS        = [42, 123, 456, 789, 999]
NUM_BLOCKS   = 1000


def run_grid():
    results = {}

    total = len(SIGMAS) * len(LAMBDAS) * len(SEEDS)
    done  = 0

    for sigma in SIGMAS:
        for lam in LAMBDAS:
            key = (sigma, lam)
            runs = []

            for seed in SEEDS:
                r = run_simulation(
                    num_blocks=NUM_BLOCKS,
                    arrival_rate=lam,
                    sigma=sigma,
                    seed=seed,
                )
                runs.append(r)
                done += 1
                print(f"  [{done}/{total}] σ={sigma}, λ={lam}, seed={seed}  "
                      f"arb_ratio={r['arbitrage']['fbamm_arb_total_profit_usdc'] / max(r['arbitrage']['univ2_arb_total_profit_usdc'], 0.01):.2f}")

            results[key] = _aggregate_runs(runs, sigma, lam)

    return results


def _aggregate_runs(runs, sigma, lam):
    def mean_std(vals):
        if len(vals) < 2:
            return vals[0] if vals else 0, 0
        return statistics.mean(vals), statistics.stdev(vals)

    arb_u  = [r["arbitrage"]["univ2_arb_total_profit_usdc"] for r in runs]
    arb_f  = [r["arbitrage"]["fbamm_arb_total_profit_usdc"]  for r in runs]
    pnl_u  = [r["lp_returns"]["univ2_net_pnl_usdc"]          for r in runs]
    pnl_f  = [r["lp_returns"]["fbamm_net_pnl_usdc"]          for r in runs]
    fees_u = [r["lp_returns"]["univ2_fees_usdc"]             for r in runs]
    fees_f = [r["lp_returns"]["fbamm_lp_fees_usdc"]          for r in runs]
    il_u   = [r["lp_returns"]["univ2_il_usdc"]               for r in runs]
    il_f   = [r["lp_returns"]["fbamm_il_usdc"]               for r in runs]
    nett   = [r["netting"]["avg_netting_ratio"]              for r in runs]
    ratio  = [f / max(u, 0.01) for u, f in zip(arb_u, arb_f)]

    mu_arb_u,  sd_arb_u  = mean_std(arb_u)
    mu_arb_f,  sd_arb_f  = mean_std(arb_f)
    mu_pnl_u,  sd_pnl_u  = mean_std(pnl_u)
    mu_pnl_f,  sd_pnl_f  = mean_std(pnl_f)
    mu_fees_u, _         = mean_std(fees_u)
    mu_fees_f, _         = mean_std(fees_f)
    mu_il_u,   _         = mean_std(il_u)
    mu_il_f,   _         = mean_std(il_f)
    mu_nett,   _         = mean_std(nett)
    mu_ratio,  sd_ratio  = mean_std(ratio)

    return {
        "sigma": sigma,
        "lambda": lam,
        "n_seeds": len(runs),
        "arb_univ2_mean": mu_arb_u,  "arb_univ2_std": sd_arb_u,
        "arb_fbamm_mean": mu_arb_f,  "arb_fbamm_std": sd_arb_f,
        "arb_ratio_mean": mu_ratio,  "arb_ratio_std": sd_ratio,
        "lp_pnl_univ2_mean": mu_pnl_u, "lp_pnl_univ2_std": sd_pnl_u,
        "lp_pnl_fbamm_mean": mu_pnl_f, "lp_pnl_fbamm_std": sd_pnl_f,
        "fees_univ2_mean": mu_fees_u,
        "fees_fbamm_mean": mu_fees_f,
        "il_univ2_mean": mu_il_u,
        "il_fbamm_mean": mu_il_f,
        "netting_mean": mu_nett,
    }


def print_table(results):
    # Print arb profit ratio table (FBAMM/UniV2)
    print("\n" + "=" * 80)
    print("ARBIRAGEUR PROFIT RATIO (FBAMM / UniV2) — mean over 5 seeds, 1000 blocks each")
    print("Values > 1.0 mean arb extracts MORE from FBAMM (worse for FBAMM LPs)")
    print("=" * 80)

    header = "σ \\ λ   " + "  ".join(f"λ={l:>4}" for l in LAMBDAS)
    print(header)
    print("-" * len(header))
    for sigma in SIGMAS:
        row = f"σ={sigma:.3f}  "
        for lam in LAMBDAS:
            v = results[(sigma, lam)]["arb_ratio_mean"]
            row += f"  {v:6.2f}"
        print(row)

    print("\n" + "=" * 80)
    print("LP NET PnL DIFFERENCE: FBAMM − UniV2 (USDC, +ve = FBAMM better for LPs)")
    print("=" * 80)
    print(header)
    print("-" * len(header))
    for sigma in SIGMAS:
        row = f"σ={sigma:.3f}  "
        for lam in LAMBDAS:
            u = results[(sigma, lam)]["lp_pnl_univ2_mean"]
            f = results[(sigma, lam)]["lp_pnl_fbamm_mean"]
            diff = f - u
            row += f"  {diff:+7.0f}"
        print(row)

    print("\n" + "=" * 80)
    print("AVG NETTING RATIO (FBAMM only)")
    print("=" * 80)
    print(header)
    print("-" * len(header))
    for sigma in SIGMAS:
        row = f"σ={sigma:.3f}  "
        for lam in LAMBDAS:
            v = results[(sigma, lam)]["netting_mean"]
            row += f"  {v:5.1%}"
        print(row)

    print("\n" + "=" * 80)
    print("LP FEES: UniV2 / FBAMM (USDC)")
    print("=" * 80)
    print(header)
    print("-" * len(header))
    for sigma in SIGMAS:
        row = f"σ={sigma:.3f}  "
        for lam in LAMBDAS:
            fu = results[(sigma, lam)]["fees_univ2_mean"]
            ff = results[(sigma, lam)]["fees_fbamm_mean"]
            row += f"  {fu:5.0f}/{ff:5.0f}"
        print(row)


def save_results(results):
    os.makedirs("data", exist_ok=True)
    out = {}
    for (sigma, lam), v in results.items():
        out[f"s{sigma}_l{lam}"] = v
    path = "data/sensitivity_results.json"
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    print(f"Running {len(SIGMAS) * len(LAMBDAS) * len(SEEDS)} simulations "
          f"({len(SIGMAS)} σ × {len(LAMBDAS)} λ × {len(SEEDS)} seeds, "
          f"{NUM_BLOCKS} blocks each)…\n")
    results = run_grid()
    print_table(results)
    save_results(results)

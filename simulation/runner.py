"""Simulation runner: feeds ZI traders + arbitrageur to both UniV2 and FBAMM.

Architecture:
1. CEX price follows GBM (external reference / "true price")
2. ZI noise traders arrive via Poisson process with random sizes
3. Arbitrageur monitors CEX-AMM spread and trades to close it
4. Both pools start with identical reserves, receive the same order flow
5. The ONLY difference is execution: sequential (UniV2) vs batch (FBAMM)

Key metrics:
- Execution quality (price variance, spread)
- Netting efficiency (FBAMM only)
- LP returns: fees earned - impermanent loss (using CEX as reference)
- LVR: loss-versus-rebalancing (arb profits = LP adverse selection costs)
"""

import json
import math
import os
import statistics
from pools import UniswapV2Pool, FBAMMPool
from agents import TraderPopulation, CEXPriceProcess, Arbitrageur


def run_simulation(
    num_blocks: int = 1000,
    reserve0: int = 1000 * 10**18,       # 1000 ETH
    reserve1: int = 2_000_000 * 10**6,   # 2M USDC (6 decimals)
    arrival_rate: float = 5.0,
    buy_prob: float = 0.5,
    mean_size_token0: float = 1.0,
    size_std_token0: float = 0.8,
    fee_bps: int = 30,
    sigma: float = 0.02,                 # CEX price volatility per block
    seed: int = 42,
) -> dict:
    """Run a paired simulation with CEX price process + arbitrageur."""

    initial_price = (reserve1 / 10**6) / (reserve0 / 10**18)  # human USDC/ETH

    # Pools
    univ2 = UniswapV2Pool(reserve0, reserve1, fee_bps)
    fbamm = FBAMMPool(reserve0, reserve1, fee_bps)

    # CEX price (shared — same "true price" for both pools)
    cex = CEXPriceProcess(initial_price, mu=0.0, sigma=sigma, seed=seed + 1000)

    # Arbitrageurs (one per pool, same logic)
    arb_univ2 = Arbitrageur("arb_univ2", max_size_token0=50.0, fee_bps=fee_bps)
    arb_fbamm = Arbitrageur("arb_fbamm", max_size_token0=50.0, fee_bps=fee_bps)

    # ZI traders
    pop = TraderPopulation(
        num_traders=200,
        arrival_rate=arrival_rate,
        buy_prob=buy_prob,
        mean_size=mean_size_token0,
        size_std=size_std_token0,
        seed=seed,
    )

    # Track LP value over time for IL calculation
    initial_value_token1 = reserve0 * int(initial_price * 10**6) // 10**18 + reserve1
    univ2_arb_profits = 0  # total arb profit extracted from UniV2 (= LVR)
    fbamm_arb_profits = 0

    block_metrics = []

    for block in range(num_blocks):
        # 1. CEX price moves
        cex_price = cex.step()

        # 2. ZI traders arrive
        orders = pop.generate_block_orders(block)

        # Track UniV2 per-trade prices
        univ2_prices = []

        # Pre-compute order amounts using CEX price (same intent for both pools)
        order_amounts = []
        for trader_id, is_buy, size_eth in orders:
            if is_buy:
                # Trader wants to buy size_eth of token0 — brings USDC at CEX price
                amount_in = int(size_eth * cex_price * 10**6)  # USDC raw
                if amount_in <= 0:
                    continue
                order_amounts.append((trader_id, True, amount_in))
            else:
                amount_in = int(size_eth * 10**18)  # ETH raw
                if amount_in <= 0:
                    continue
                order_amounts.append((trader_id, False, amount_in))

        # === UniV2: sequential execution ===
        for trader_id, is_buy, amount_in in order_amounts:
            out = univ2.swap(block, is_buy, amount_in)
            if out > 0:
                if is_buy:
                    price = (amount_in / 10**6) / (out / 10**18)
                else:
                    price = (out / 10**6) / (amount_in / 10**18)
                univ2_prices.append(price)

        # Arbitrageur trades on UniV2 (after ZI traders, like real MEV)
        arb_trade_univ2 = arb_univ2.compute_arb_trade(
            cex_price, univ2.reserve0, univ2.reserve1)
        if arb_trade_univ2:
            is_buy, amount_in, profit = arb_trade_univ2
            univ2.swap(block, is_buy, amount_in)
            univ2_arb_profits += profit

        # === FBAMM: batch execution ===
        # Same order amounts go to FBAMM
        for trader_id, is_buy, amount_in in order_amounts:
            fbamm.swap(trader_id, is_buy, amount_in)

        # Arbitrageur also queues on FBAMM (lands in batch with everyone else)
        arb_trade_fbamm = arb_fbamm.compute_arb_trade(
            cex_price, fbamm.reserve0, fbamm.reserve1)
        fbamm_arb_amount_in = None
        fbamm_arb_is_buy = None
        if arb_trade_fbamm:
            is_buy, amount_in, expected_profit = arb_trade_fbamm
            fbamm.swap("arb_fbamm", is_buy, amount_in)
            fbamm_arb_amount_in = amount_in
            fbamm_arb_is_buy = is_buy

        # Clear FBAMM batch
        clear_result = fbamm.clear(block)

        # Compute actual arb profit on FBAMM from clearing result
        if arb_trade_fbamm and clear_result:
            if fbamm_arb_is_buy:
                arb_out = clear_result["buyer_outputs"].get("arb_fbamm", 0)
                # Profit: sell arb_out token0 on CEX at cex_price, minus cost
                revenue = int(arb_out * cex_price / 10**12)  # raw token1
                fee = (fbamm_arb_amount_in * 30) // 10000
                cost = fbamm_arb_amount_in - fee  # net amount that was in the batch
                actual_profit = revenue - fbamm_arb_amount_in  # vs total paid including fee
                fbamm_arb_profits += max(0, actual_profit)
            else:
                arb_out = clear_result["seller_outputs"].get("arb_fbamm", 0)
                fee = (fbamm_arb_amount_in * 30) // 10000
                cost = int(fbamm_arb_amount_in * cex_price / 10**12)
                actual_profit = arb_out - cost
                fbamm_arb_profits += max(0, actual_profit)

        # === Block metrics ===
        bm = {
            "block": block,
            "cex_price": cex_price,
            "num_zi_orders": len(orders),
            "univ2_spot": (univ2.reserve1 * 10**12) / univ2.reserve0,
            "fbamm_spot": (fbamm.reserve1 * 10**12) / fbamm.reserve0,
        }

        if len(univ2_prices) >= 2:
            bm["univ2_price_variance"] = statistics.variance(univ2_prices)
            bm["univ2_spread"] = max(univ2_prices) - min(univ2_prices)
        elif len(univ2_prices) == 1:
            bm["univ2_price_variance"] = 0
            bm["univ2_spread"] = 0

        if clear_result:
            bm["fbamm_netting_ratio"] = clear_result["netting_ratio"]
            bm["fbamm_num_buyers"] = clear_result["num_buyers"]
            bm["fbamm_num_sellers"] = clear_result["num_sellers"]

        bm["univ2_arb_traded"] = arb_trade_univ2 is not None
        bm["fbamm_arb_traded"] = arb_trade_fbamm is not None

        block_metrics.append(bm)

    # === Compute IL ===
    final_cex_price = cex.price

    # IL = value_if_held - value_in_pool
    # value_if_held = initial_reserve0 * final_price + initial_reserve1
    # value_in_pool = current_reserve0 * final_price + current_reserve1
    held_value = reserve0 * int(final_cex_price * 10**6) // 10**18 + reserve1
    univ2_pool_value = univ2.reserve0 * int(final_cex_price * 10**6) // 10**18 + univ2.reserve1
    fbamm_pool_value = fbamm.reserve0 * int(final_cex_price * 10**6) // 10**18 + fbamm.reserve1

    univ2_il = held_value - univ2_pool_value  # positive = LP lost value
    fbamm_il = held_value - fbamm_pool_value

    return _aggregate(univ2, fbamm, cex, arb_univ2, arb_fbamm,
                      block_metrics, num_blocks, initial_price,
                      held_value, univ2_pool_value, fbamm_pool_value,
                      univ2_il, fbamm_il, univ2_arb_profits, fbamm_arb_profits)


def _aggregate(univ2, fbamm, cex, arb_univ2, arb_fbamm,
               block_metrics, num_blocks, initial_price,
               held_value, univ2_pool_value, fbamm_pool_value,
               univ2_il, fbamm_il, univ2_arb_profits, fbamm_arb_profits) -> dict:

    traded = [b for b in block_metrics if b.get("num_zi_orders", 0) > 0]
    multi = [b for b in traded if b.get("univ2_price_variance") is not None
             and b["univ2_price_variance"] > 0]
    netting = [b for b in block_metrics if b.get("fbamm_netting_ratio") is not None]
    both = [b for b in netting
            if b.get("fbamm_num_buyers", 0) > 0 and b.get("fbamm_num_sellers", 0) > 0]

    variances = [b["univ2_price_variance"] for b in multi]
    spreads = [b["univ2_spread"] for b in multi if "univ2_spread" in b]
    netting_ratios = [b["fbamm_netting_ratio"] for b in netting]

    arb_blocks_univ2 = sum(1 for b in block_metrics if b.get("univ2_arb_traded"))
    arb_blocks_fbamm = sum(1 for b in block_metrics if b.get("fbamm_arb_traded"))

    return {
        "config": {
            "num_blocks": num_blocks,
            "initial_price": initial_price,
            "final_cex_price": cex.price,
            "sigma": cex.sigma,
        },
        "summary": {
            "total_blocks_with_trades": len(traded),
            "multi_trade_blocks": len(multi),
            "avg_trades_per_block": statistics.mean([b["num_zi_orders"] for b in traded]) if traded else 0,
        },
        "execution_quality": {
            "univ2_avg_price_variance": statistics.mean(variances) if variances else 0,
            "univ2_max_price_variance": max(variances) if variances else 0,
            "univ2_avg_spread": statistics.mean(spreads) if spreads else 0,
            "univ2_max_spread": max(spreads) if spreads else 0,
            "fbamm_price_variance": 0,
            "fbamm_spread": 0,
        },
        "netting": {
            "avg_netting_ratio": statistics.mean(netting_ratios) if netting_ratios else 0,
            "max_netting_ratio": max(netting_ratios) if netting_ratios else 0,
            "blocks_with_both_sides": len(both),
            "blocks_with_both_sides_pct": len(both) / len(netting) * 100 if netting else 0,
        },
        "arbitrage": {
            "univ2_arb_blocks": arb_blocks_univ2,
            "fbamm_arb_blocks": arb_blocks_fbamm,
            "univ2_arb_total_profit_usdc": univ2_arb_profits / 10**6,
            "fbamm_arb_total_profit_usdc": fbamm_arb_profits / 10**6,
        },
        "lp_returns": {
            "held_value_usdc": held_value / 10**6,
            "univ2_pool_value_usdc": univ2_pool_value / 10**6,
            "fbamm_pool_value_usdc": fbamm_pool_value / 10**6,
            "univ2_il_usdc": univ2_il / 10**6,
            "fbamm_il_usdc": fbamm_il / 10**6,
            "univ2_fees_usdc": (int(univ2.total_fees0) * int(cex.price * 10**6) // 10**18
                                + int(univ2.total_fees1)) / 10**6,
            "fbamm_lp_fees_usdc": (int(fbamm.total_lp_fees0) * int(cex.price * 10**6) // 10**18
                                   + int(fbamm.total_lp_fees1)) / 10**6,
            "univ2_net_pnl_usdc": (-univ2_il + int(univ2.total_fees0) * int(cex.price * 10**6) // 10**18
                                   + int(univ2.total_fees1)) / 10**6,
            "fbamm_net_pnl_usdc": (-fbamm_il + int(fbamm.total_lp_fees0) * int(cex.price * 10**6) // 10**18
                                   + int(fbamm.total_lp_fees1)) / 10**6,
        },
        "pool_state": {
            "univ2_reserves": f"{univ2.reserve0 / 10**18:.2f} ETH / {univ2.reserve1 / 10**6:.2f} USDC",
            "fbamm_reserves": f"{fbamm.reserve0 / 10**18:.2f} ETH / {fbamm.reserve1 / 10**6:.2f} USDC",
        },
        "block_metrics": block_metrics,
    }


def print_summary(r: dict):
    s = r["summary"]
    eq = r["execution_quality"]
    n = r["netting"]
    a = r["arbitrage"]
    lp = r["lp_returns"]

    print("=" * 65)
    print("FBAMM vs UniswapV2 — Agent Simulation (ZI + Arbitrageur + GBM)")
    print("=" * 65)
    print(f"Blocks: {r['config']['num_blocks']} | "
          f"CEX σ={r['config']['sigma']} | "
          f"Price: ${r['config']['initial_price']:.0f} → ${r['config']['final_cex_price']:.0f}")
    print(f"Blocks with trades: {s['total_blocks_with_trades']} | "
          f"Avg trades/block: {s['avg_trades_per_block']:.1f}")
    print()

    print("--- Execution Quality ---")
    print(f"  UniV2 avg price variance: {eq['univ2_avg_price_variance']:.2f}")
    print(f"  UniV2 avg spread:         ${eq['univ2_avg_spread']:.2f}")
    print(f"  FBAMM price variance:     0 (unified price)")
    print()

    print("--- Netting ---")
    print(f"  Avg netting ratio:   {n['avg_netting_ratio']:.2%}")
    print(f"  Max netting ratio:   {n['max_netting_ratio']:.2%}")
    print(f"  Both-side blocks:    {n['blocks_with_both_sides']} ({n['blocks_with_both_sides_pct']:.1f}%)")
    print()

    print("--- Arbitrage (LVR) ---")
    print(f"  UniV2 arb blocks:    {a['univ2_arb_blocks']}")
    print(f"  FBAMM arb blocks:    {a['fbamm_arb_blocks']}")
    print(f"  UniV2 arb profit:    ${a['univ2_arb_total_profit_usdc']:,.2f}")
    print(f"  FBAMM arb profit:    ${a['fbamm_arb_total_profit_usdc']:,.2f}")
    print()

    print("--- LP Returns ---")
    print(f"  HODL value:          ${lp['held_value_usdc']:,.2f}")
    print(f"  UniV2 pool value:    ${lp['univ2_pool_value_usdc']:,.2f}")
    print(f"  FBAMM pool value:    ${lp['fbamm_pool_value_usdc']:,.2f}")
    print(f"  UniV2 IL:            ${lp['univ2_il_usdc']:,.2f}")
    print(f"  FBAMM IL:            ${lp['fbamm_il_usdc']:,.2f}")
    print(f"  UniV2 fees earned:   ${lp['univ2_fees_usdc']:,.2f}")
    print(f"  FBAMM LP fees:       ${lp['fbamm_lp_fees_usdc']:,.2f}")
    print(f"  UniV2 net PnL:       ${lp['univ2_net_pnl_usdc']:,.2f}")
    print(f"  FBAMM net PnL:       ${lp['fbamm_net_pnl_usdc']:,.2f}")
    print()
    print(f"  Reserves: {r['pool_state']['univ2_reserves']} (UniV2)")
    print(f"            {r['pool_state']['fbamm_reserves']} (FBAMM)")


if __name__ == "__main__":
    import sys

    num_blocks = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    arrival_rate = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    sigma = float(sys.argv[3]) if len(sys.argv) > 3 else 0.02
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 42

    print(f"Config: {num_blocks} blocks, λ={arrival_rate}, σ={sigma}, seed={seed}\n")

    results = run_simulation(
        num_blocks=num_blocks,
        arrival_rate=arrival_rate,
        sigma=sigma,
        seed=seed,
    )

    print_summary(results)

    os.makedirs("data", exist_ok=True)
    out_path = f"data/sim_{num_blocks}b_l{arrival_rate}_s{sigma}_seed{seed}.json"
    save = {k: v for k, v in results.items() if k != "block_metrics"}
    with open(out_path, "w") as f:
        json.dump(save, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")

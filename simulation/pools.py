"""AMM pool implementations: UniswapV2 and FBAMM.

Both pools use the constant-product formula (x * y = k).
The key difference is execution: UniV2 executes each swap immediately,
while FBAMM batches swaps per block and clears at a unified price.
"""


class UniswapV2Pool:
    """Standard constant-product AMM with sequential execution."""

    def __init__(self, reserve0: int, reserve1: int, fee_bps: int = 30):
        self.reserve0 = reserve0
        self.reserve1 = reserve1
        self.fee_bps = fee_bps
        self.total_fees0 = 0
        self.total_fees1 = 0
        self.trade_log = []  # (block, direction, amount_in, amount_out, price)

    def swap(self, block: int, is_buy: bool, amount_in: int) -> int:
        """Execute a swap immediately. is_buy=True means buy token0 with token1."""
        fee = (amount_in * self.fee_bps) // 10000
        net = amount_in - fee

        if is_buy:
            # token1 in, token0 out
            amount_out = (net * self.reserve0) // (self.reserve1 + net)
            self.reserve1 += net + fee  # fee stays in reserves (like UniV2)
            self.reserve0 -= amount_out
            self.total_fees1 += fee
            price = amount_in / amount_out if amount_out > 0 else float('inf')
        else:
            # token0 in, token1 out
            amount_out = (net * self.reserve1) // (self.reserve0 + net)
            self.reserve0 += net + fee
            self.reserve1 -= amount_out
            self.total_fees0 += fee
            price = amount_out / amount_in if amount_in > 0 else 0

        self.trade_log.append((block, is_buy, amount_in, amount_out, price))
        return amount_out

    def spot_price(self) -> float:
        """Current spot price: token1 per token0."""
        return self.reserve1 / self.reserve0

    def k(self) -> int:
        return self.reserve0 * self.reserve1


class FBAMMPool:
    """Frequent Batch Auction AMM with per-block clearing."""

    def __init__(self, reserve0: int, reserve1: int, fee_bps: int = 30,
                 lp_fee_share: int = 80):
        self.reserve0 = reserve0
        self.reserve1 = reserve1
        self.fee_bps = fee_bps
        self.lp_fee_share = lp_fee_share

        # Batch state
        self.Qb = 0  # token1 deposited by buyers
        self.Qs = 0  # token0 deposited by sellers
        self.pending_fees0 = 0
        self.pending_fees1 = 0
        self.buy_orders = {}   # trader_id -> amount
        self.sell_orders = {}  # trader_id -> amount

        # Tracking
        self.total_lp_fees0 = 0
        self.total_lp_fees1 = 0
        self.total_clearer_fees0 = 0
        self.total_clearer_fees1 = 0
        self.clear_log = []  # per-block clearing results
        self.trade_log = []  # per-trade results (filled after clearing)

    def swap(self, trader_id: str, is_buy: bool, amount_in: int):
        """Queue a swap into the batch. Does not execute."""
        fee = (amount_in * self.fee_bps) // 10000
        net = amount_in - fee

        if is_buy:
            self.pending_fees1 += fee
            self.Qb += net
            self.buy_orders[trader_id] = self.buy_orders.get(trader_id, 0) + net
        else:
            self.pending_fees0 += fee
            self.Qs += net
            self.sell_orders[trader_id] = self.sell_orders.get(trader_id, 0) + net

    def clear(self, block: int) -> dict:
        """Execute batch clearing. Returns metrics dict."""
        if self.Qb == 0 and self.Qs == 0:
            return None

        _Qb = self.Qb
        _Qs = self.Qs
        r0 = self.reserve0
        r1 = self.reserve1

        # Cross-decimal netting: compare Qb*r0 vs Qs*r1
        buy_excess = _Qb * r0 >= _Qs * r1
        amount_out = 0

        if buy_excess:
            matched_token1 = (_Qs * r1) // r0
            net_demand = _Qb - matched_token1
            if net_demand > 0:
                amount_out = (net_demand * r0) // (r1 + net_demand)
                self.reserve1 += net_demand
                self.reserve0 -= amount_out
            total_token0_for_buyers = _Qs + amount_out
            total_token1_for_sellers = matched_token1
        else:
            matched_token0 = (_Qb * r0) // r1
            net_demand = _Qs - matched_token0
            if net_demand > 0:
                amount_out = (net_demand * r1) // (r0 + net_demand)
                self.reserve0 += net_demand
                self.reserve1 -= amount_out
            total_token0_for_buyers = matched_token0
            total_token1_for_sellers = _Qb + amount_out

        # Distribute to traders (compute per-trader outputs)
        buyer_outputs = {}
        for tid, share in self.buy_orders.items():
            payout = (share * total_token0_for_buyers) // _Qb if _Qb > 0 else 0
            buyer_outputs[tid] = payout
            self.trade_log.append((block, True, share, payout,
                                   share / payout if payout > 0 else float('inf')))

        seller_outputs = {}
        for tid, share in self.sell_orders.items():
            payout = (share * total_token1_for_sellers) // _Qs if _Qs > 0 else 0
            seller_outputs[tid] = payout
            self.trade_log.append((block, False, share, payout,
                                   payout / share if share > 0 else 0))

        # Fee distribution
        lp_fee0 = (self.pending_fees0 * self.lp_fee_share) // 100
        lp_fee1 = (self.pending_fees1 * self.lp_fee_share) // 100
        clearer_fee0 = self.pending_fees0 - lp_fee0
        clearer_fee1 = self.pending_fees1 - lp_fee1

        self.reserve0 += lp_fee0
        self.reserve1 += lp_fee1
        self.total_lp_fees0 += lp_fee0
        self.total_lp_fees1 += lp_fee1
        self.total_clearer_fees0 += clearer_fee0
        self.total_clearer_fees1 += clearer_fee1

        # Netting ratio (in token0 terms)
        buy_as_token0 = (_Qb * r0) // r1 if r1 > 0 else 0
        netted = min(buy_as_token0, _Qs)
        total = max(buy_as_token0, _Qs)
        netting_ratio = netted / total if total > 0 else 0

        result = {
            "block": block,
            "Qb": _Qb,
            "Qs": _Qs,
            "netting_ratio": netting_ratio,
            "amount_out_from_amm": amount_out,
            "num_buyers": len(self.buy_orders),
            "num_sellers": len(self.sell_orders),
            "total_token0_for_buyers": total_token0_for_buyers,
            "total_token1_for_sellers": total_token1_for_sellers,
            "buyer_outputs": buyer_outputs,
            "seller_outputs": seller_outputs,
        }

        self.clear_log.append(result)

        # Reset batch
        self.Qb = 0
        self.Qs = 0
        self.pending_fees0 = 0
        self.pending_fees1 = 0
        self.buy_orders.clear()
        self.sell_orders.clear()

        return result

    def spot_price(self) -> float:
        """Current spot price: token1 per token0."""
        return self.reserve1 / self.reserve0

    def k(self) -> int:
        return self.reserve0 * self.reserve1

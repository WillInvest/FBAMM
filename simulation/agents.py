"""Trader agents for AMM simulation.

Agent types:
- ZI (Zero Intelligence): random direction + size, no strategy (Gode & Sunder 1993)
- Arbitrageur: monitors CEX-AMM spread, trades to close the gap
- CEXPriceProcess: GBM-based external reference price

References:
- Gode & Sunder (1993) — ZI traders
- Milionis et al. (2022) — LVR framework, arbitrageur model
- Budish, Cramton & Shim (2015) — frequent batch auctions
"""

import random
import math


class ZITrader:
    """Zero Intelligence trader.

    Submits market orders with:
    - Random direction (buy or sell) with configurable bias
    - Random size drawn from a log-normal distribution
    - No information about price, no strategy, no memory

    This is the baseline agent that tests whether the AMM's structural
    properties (netting, unified pricing) create value even without
    strategic behavior.
    """

    def __init__(self, trader_id: str, buy_prob: float = 0.5,
                 mean_size: float = 1.0, size_std: float = 0.5,
                 rng: random.Random = None):
        """
        Args:
            trader_id: unique identifier
            buy_prob: probability of buying token0 (vs selling)
            mean_size: mean order size in token units (log-normal mu parameter)
            size_std: order size std dev (log-normal sigma parameter)
            rng: random number generator (for reproducibility)
        """
        self.trader_id = trader_id
        self.buy_prob = buy_prob
        self.mean_size = mean_size
        self.size_std = size_std
        self.rng = rng or random.Random()

    def generate_order(self) -> tuple:
        """Generate a random order.

        Returns:
            (is_buy: bool, size: float) where size is in the input token's units
        """
        is_buy = self.rng.random() < self.buy_prob

        # Log-normal size distribution (always positive, right-skewed like real order sizes)
        # mu and sigma for log-normal such that mean ≈ mean_size
        sigma = math.sqrt(math.log(1 + (self.size_std / self.mean_size) ** 2))
        mu = math.log(self.mean_size) - sigma ** 2 / 2
        size = self.rng.lognormvariate(mu, sigma)

        return is_buy, size


class CEXPriceProcess:
    """External reference price following Geometric Brownian Motion.

    P(t+1) = P(t) * exp((mu - sigma^2/2)*dt + sigma*sqrt(dt)*Z)

    This models the "true" price on a centralized exchange. The AMM's spot
    price should track this (corrected by arbitrageurs). The divergence
    between AMM spot and CEX price is the source of LVR.
    """

    def __init__(self, initial_price: float, mu: float = 0.0,
                 sigma: float = 0.02, dt: float = 1.0, seed: int = 99):
        """
        Args:
            initial_price: starting price (token1 per token0), e.g. 2000 for ETH/USDC
            mu: drift (annualized). 0 = no trend.
            sigma: volatility per sqrt(dt). 0.02 = 2% per block.
            dt: time step (1 block = 1 unit)
            seed: random seed
        """
        self.price = initial_price
        self.mu = mu
        self.sigma = sigma
        self.dt = dt
        self.rng = random.Random(seed)
        self.price_history = [initial_price]

    def step(self) -> float:
        """Advance one time step, return new price."""
        z = self.rng.gauss(0, 1)
        self.price *= math.exp(
            (self.mu - self.sigma**2 / 2) * self.dt + self.sigma * math.sqrt(self.dt) * z
        )
        self.price_history.append(self.price)
        return self.price


class Arbitrageur:
    """Arbitrageur that trades to close the CEX-AMM spread.

    Monitors the gap between CEX price and AMM spot price. When the gap
    exceeds a threshold (covering fees), trades to profit from the
    discrepancy. This is the standard model from Milionis et al. (2022).

    The arb is the key differentiator between UniV2 and FBAMM:
    - On UniV2: arb executes immediately, extracts full LVR
    - On FBAMM: arb's trade lands in the batch with ZI traders,
      netting partially offsets the arb's price impact
    """

    def __init__(self, trader_id: str = "arb_0", max_size_token0: float = 10.0,
                 fee_bps: int = 30):
        """
        Args:
            trader_id: unique identifier
            max_size_token0: maximum trade size in token0 units per block
            fee_bps: AMM fee in basis points (used to calculate threshold)
        """
        self.trader_id = trader_id
        self.max_size_token0 = max_size_token0
        self.fee_threshold = fee_bps / 10000  # need spread > fee to profit
        self.total_profit_token1 = 0  # track cumulative arb profit in token1

    def compute_arb_trade(self, cex_price: float, amm_reserve0: int,
                          amm_reserve1: int) -> tuple:
        """Determine if an arb opportunity exists and compute the optimal trade.

        Args:
            cex_price: current CEX price (token1 per token0, human-readable)
            amm_reserve0: AMM reserve of token0 (raw units)
            amm_reserve1: AMM reserve of token1 (raw units)

        Returns:
            (is_buy, amount_in_raw, expected_profit_token1) or None if no opportunity
        """
        # AMM spot price in human-readable terms
        # spot = reserve1 / reserve0 but adjusted for decimals
        # We work in raw units throughout to match the pool
        # spot_raw = reserve1 / reserve0
        # For 18/6 decimal pair: spot_human = (reserve1/1e6) / (reserve0/1e18) = reserve1 * 1e12 / reserve0
        amm_spot = (amm_reserve1 * 10**12) / amm_reserve0  # human USDC per ETH

        spread = (cex_price - amm_spot) / amm_spot

        if abs(spread) <= self.fee_threshold:
            return None  # spread too small to cover fees

        if spread > 0:
            # CEX price > AMM price → AMM is cheap → buy token0 on AMM, sell on CEX
            is_buy = True
            # Optimal arb size: trade until AMM price = CEX price (minus fees)
            # For constant product: new_spot = (r1 + amount_in) / (r0 - amount_out)
            # Target: new_spot_human = cex_price
            # Approximate: trade size proportional to spread
            target_r1_over_r0 = cex_price / 10**12  # convert back to raw ratio
            # After trade: (r1 + net_in) * (r0 - out) = r0 * r1 = k
            # new_spot_raw = (r1 + net_in) / (r0 - out)
            # We want new_spot_raw = target_r1_over_r0
            # From constant product: out = net_in * r0 / (r1 + net_in)
            # new_r0 = r0 - out = r0 * r1 / (r1 + net_in)
            # new_r1 = r1 + net_in
            # new_spot_raw = (r1 + net_in)^2 / (r0 * r1)
            # Set equal to target: (r1 + net_in)^2 = target * r0 * r1
            # net_in = sqrt(target * r0 * r1) - r1
            net_in_raw = int(math.sqrt(target_r1_over_r0 * amm_reserve0 * amm_reserve1) - amm_reserve1)
            if net_in_raw <= 0:
                return None

            # Cap at max size (converted to token1 at cex price)
            max_in_raw = int(self.max_size_token0 * cex_price * 10**6)  # USDC raw
            net_in_raw = min(net_in_raw, max_in_raw)

            # Gross up for fee: amount_in = net_in / (1 - fee_rate)
            amount_in_raw = (net_in_raw * 10000) // (10000 - 30)

            # Expected output from AMM
            fee = (amount_in_raw * 30) // 10000
            net = amount_in_raw - fee
            amount_out_raw = (net * amm_reserve0) // (amm_reserve1 + net)

            # Profit: sell amount_out on CEX at cex_price, minus what we paid
            revenue_token1 = int(amount_out_raw * cex_price / 10**12)  # raw token1
            cost_token1 = amount_in_raw
            profit = revenue_token1 - cost_token1

            if profit <= 0:
                return None

            return (True, amount_in_raw, profit)

        else:
            # CEX price < AMM price → AMM is expensive → sell token0 on AMM, buy on CEX
            is_buy = False
            target_r1_over_r0 = cex_price / 10**12

            # After selling token0: new_r0 = r0 + net_in, new_r1 = r0*r1/(r0+net_in)
            # new_spot_raw = r0*r1 / (r0+net_in)^2
            # Set = target: net_in = sqrt(r0*r1/target) - r0
            if target_r1_over_r0 <= 0:
                return None
            net_in_raw = int(math.sqrt(amm_reserve0 * amm_reserve1 / target_r1_over_r0) - amm_reserve0)
            if net_in_raw <= 0:
                return None

            max_in_raw = int(self.max_size_token0 * 10**18)  # ETH raw
            net_in_raw = min(net_in_raw, max_in_raw)

            amount_in_raw = (net_in_raw * 10000) // (10000 - 30)

            fee = (amount_in_raw * 30) // 10000
            net = amount_in_raw - fee
            amount_out_raw = (net * amm_reserve1) // (amm_reserve0 + net)

            # Cost: buy amount_in token0 on CEX
            cost_token1 = int(amount_in_raw * cex_price / 10**12)  # raw token1
            revenue_token1 = amount_out_raw
            profit = revenue_token1 - cost_token1

            if profit <= 0:
                return None

            return (False, amount_in_raw, profit)


class TraderPopulation:
    """A population of ZI traders with configurable arrival process.

    Models trader arrivals as a Poisson process: each block has a random
    number of traders arriving, drawn from Poisson(lambda).
    """

    def __init__(self, num_traders: int = 100, arrival_rate: float = 3.0,
                 buy_prob: float = 0.5, mean_size: float = 1.0,
                 size_std: float = 0.5, seed: int = 42):
        """
        Args:
            num_traders: size of trader pool
            arrival_rate: average number of traders per block (Poisson lambda)
            buy_prob: probability each trader buys (vs sells)
            mean_size: mean order size
            size_std: order size standard deviation
            seed: random seed for reproducibility
        """
        self.rng = random.Random(seed)
        self.arrival_rate = arrival_rate
        self.traders = [
            ZITrader(
                trader_id=f"zi_{i}",
                buy_prob=buy_prob,
                mean_size=mean_size,
                size_std=size_std,
                rng=random.Random(seed + i + 1),
            )
            for i in range(num_traders)
        ]

    def generate_block_orders(self, block: int) -> list:
        """Generate orders for one block.

        Returns:
            list of (trader_id, is_buy, size_in_native_units)
        """
        # Poisson arrival: number of traders this block
        n_arrivals = self._poisson(self.arrival_rate)
        n_arrivals = min(n_arrivals, len(self.traders))

        # Select random traders
        arriving = self.rng.sample(self.traders, n_arrivals)

        orders = []
        for trader in arriving:
            is_buy, size = trader.generate_order()
            orders.append((trader.trader_id, is_buy, size))

        return orders

    def _poisson(self, lam: float) -> int:
        """Generate Poisson random variable using Knuth's algorithm."""
        L = math.exp(-lam)
        k = 0
        p = 1.0
        while True:
            k += 1
            p *= self.rng.random()
            if p <= L:
                return k - 1

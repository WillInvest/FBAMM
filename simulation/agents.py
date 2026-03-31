"""Trader agents for AMM simulation.

Starting with Zero Intelligence (ZI) traders following Gode & Sunder (1993).
ZI traders submit orders with random direction and size, drawn from
configurable distributions.
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

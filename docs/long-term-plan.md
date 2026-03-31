# FBAMM Long-Term Plan

**Last updated:** 2026-03-31
**Objectives:**
1. Working FBAMM on Anvil testnet with backtest pipeline
2. Publication-ready academic paper

## Current Status

Phase 1: Foundation — core contract implemented, test suite built, backtest infrastructure in progress.

## Priority Backlog

### High Priority
- [ ] Complete Anvil-based per-block replay (Python orchestrator calling forge/cast)
- [ ] Run first backtest on ETH/USDC (100 blocks)
- [ ] Implement FBAMM execution quality metrics in aggregate.py
- [ ] Compare FBAMM unified price vs Uniswap V2 per-trade prices

### Medium Priority
- [ ] Expand backtest to ETH/USDT and ETH/WBTC pools
- [ ] Implement LP return comparison (fee income - IL)
- [ ] Fetch MEV data from Flashbots/EigenPhi for test period
- [ ] Gas optimization for clear() if needed
- [ ] Add netting efficiency analysis

### Low Priority (Paper)
- [ ] Write Introduction and Related Work sections
- [ ] Formalize MEV elimination theorem
- [ ] Create per-block comparison methodology diagram
- [ ] Expand to 10,000+ block sample
- [ ] Identify and add high-MEV token pairs
- [ ] Sepolia deployment

## Completed Work

- [2026-03-31] Project design spec finalized
- [2026-03-31] Implementation plan created
- [2026-03-31] Foundry project setup (forge, OpenZeppelin, MockERC20)
- [2026-03-31] FBAMM.sol core: addLiquidity, removeLiquidity, swap, clear
- [2026-03-31] Test suite: unit tests, fuzz tests, invariant tests, gas benchmarks
- [2026-03-31] Backtest pipeline: swap fetcher + per-block replay orchestrator
- [2026-03-31] Analysis scripts: aggregate.py + plot.py

## Session Log

### Session 1 (2026-03-31)
- Created design spec and implementation plan
- Implemented full FBAMM contract with TDD
- Built backtest and analysis pipeline
- **Suggestion for next session:** Run first backtest on ETH/USDC with 100 blocks. This will validate the entire pipeline and give us the first data points. Set up RPC key if not done yet.

## Open Questions
- What block range gives the best mix of high/low volatility for the paper?
- Should we compare against Uniswap V3 as well, or keep scope to V2?
- What's the optimal fee split (80/20) or should we test multiple splits?

## Ideas
- Test different fee splits (70/30, 90/10) and compare LP returns
- Analyze netting ratio as a function of block activity — does it scale?
- Compare gas overhead of FBAMM vs direct swap + MEV cost

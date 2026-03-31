# FBAMM Long-Term Plan

**Last updated:** 2026-03-31
**Objectives:**
1. Working FBAMM on Anvil testnet with backtest pipeline
2. Publication-ready academic paper

## Current Status

Phase 1 complete. Core contract, test suite, and backtest infrastructure all built. Cross-decimal netting fixed. Python simulation validated against Solidity contract (exact match). Ready for first real backtest once RPC key is configured.

## Priority Backlog

### High Priority (Next Session)
- [ ] Set up RPC key (dRPC or Alchemy) in .env
- [ ] Run first backtest on ETH/USDC (100 blocks) — validate entire pipeline end-to-end
- [ ] Implement full Anvil-based per-block replay (Python orchestrator using cast send/call)
- [ ] Compare FBAMM unified price vs Uniswap V2 per-trade prices with real data

### Medium Priority
- [ ] Expand backtest to ETH/USDT and ETH/WBTC pools
- [ ] Implement LP return comparison (fee income - impermanent loss)
- [ ] Fetch MEV data from Flashbots/EigenPhi for quantification
- [ ] Gas optimization for clear() if benchmarks show issues
- [ ] Add netting efficiency analysis across different pool types

### Low Priority (Paper)
- [ ] Write Introduction and Related Work sections
- [ ] Formalize MEV elimination theorem (mathematical proof)
- [ ] Create per-block comparison methodology diagram
- [ ] Expand to 10,000+ block sample for statistical significance
- [ ] Identify and add high-MEV token pairs
- [ ] Sepolia testnet deployment
- [ ] LaTeX paper skeleton

## Completed Work

- [2026-03-31] Project design spec finalized
- [2026-03-31] Implementation plan created (10 tasks)
- [2026-03-31] Foundry project setup (forge, OpenZeppelin, MockERC20)
- [2026-03-31] FBAMM.sol core: addLiquidity, removeLiquidity, swap, clear
- [2026-03-31] Test suite: 32 tests (unit, fuzz 256 runs, invariant 128K calls, gas benchmarks)
- [2026-03-31] Backtest pipeline: fetch_swaps.py + backtest.py + aggregate.py + plot.py
- [2026-03-31] Fixed cross-decimal netting bug (Qb*r0 vs Qs*r1 comparison)
- [2026-03-31] Cross-validation: Python simulation matches Solidity contract exactly
- [2026-03-31] Integration tests: multi-trader scenarios with UniV2 comparison
- [2026-03-31] Strengthened test assertions: exact value checks for clear() payouts and fees
- [2026-03-31] GitHub repo: https://github.com/WillInvest/FBAMM.git
- [2026-03-31] Cron job configured for autonomous development loop

## Session Log

### Session 1 (2026-03-31)
- Created design spec and implementation plan
- Implemented full FBAMM contract with TDD (10 tasks, all complete)
- Built backtest and analysis pipeline
- Discovered and fixed cross-decimal netting bug
- Cross-validated Python backtest against Solidity (exact match)
- Pushed to GitHub, set up cron for autonomous loop
- **Suggestion for next session:** Run first backtest on ETH/USDC. If RPC key is available in .env, run `python3 analysis/fetch_swaps.py ETH_USDC 19000000 19000100` then `python3 analysis/backtest.py data/ETH_USDC_19000000_19000100.json`. If no RPC key, focus on: (1) writing the MEV elimination theorem proof, (2) expanding the Anvil integration to use cast for on-chain verification, (3) starting the paper's Introduction section.

## Open Questions
- What block range gives the best mix of high/low volatility for the paper?
- Should we compare against Uniswap V3 as well, or keep scope to V2?
- What's the optimal fee split (80/20) or should we test multiple splits?
- How does netting ratio vary across pool types (major vs small-cap)?

## Ideas
- Test different fee splits (70/30, 90/10) and compare LP returns
- Analyze netting ratio as a function of block activity — does it scale?
- Compare gas overhead of FBAMM vs direct swap + MEV cost (break-even analysis)
- Formal game-theoretic analysis of clearing bounty mechanism
- Multi-block simulation with persistent state to measure long-term LP returns

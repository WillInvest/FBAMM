# FBAMM Long-Term Plan

**Last updated:** 2026-03-31
**Objectives:**
1. Working FBAMM on Anvil testnet with backtest pipeline
2. Publication-ready academic paper

## Current Status

Phase 2: Agent simulation and analysis. Core contract built. ZI trader + arbitrageur + CEX (GBM) simulation running. First results show an unexpected finding that needs investigation.

## IMPORTANT FINDING (2026-03-31)

**FBAMM does NOT reduce arbitrageur profits (LVR) vs UniswapV2.** In simulation, the arb actually extracts MORE from FBAMM ($160K) than UniV2 ($138K) because the batch clearing gives the arb a better unified price when ZI traders on the same side amplify the correction.

**FBAMM's confirmed advantage is execution quality** — unified pricing eliminates within-block price variance ($11.53 avg spread → $0). The netting efficiency is also real (25-41% avg).

**This finding needs deeper analysis:** Is the arb model correct? Does the arb's information advantage (seeing reserves before batch) invalidate the MEV protection claim? How does this compare to the FM-AMM paper (Canidio & Fritsch 2023)?

## Priority Backlog

### Critical (Address the LVR Finding)
- [ ] Analyze WHY FBAMM arb profits are higher — is this a simulation artifact or real?
- [ ] Re-read Canidio & Fritsch (2023) FM-AMM paper — how do they handle arb in batch?
- [ ] Consider: should arb submit BEFORE ZI traders (realistic: arb sees mempool) vs AFTER?
- [ ] Consider: does FBAMM need a commit-reveal scheme to truly protect against MEV?
- [ ] Run sensitivity analysis: vary sigma, arrival_rate, arb_max_size

### High Priority
- [ ] Run backtest on real ETH/USDC data (already working — data fetched)
- [ ] Expand to ETH/USDT and ETH/WBTC pools
- [ ] Implement LP return comparison (fee income - impermanent loss) over time series
- [ ] Add MEV/sandwich bot agent to simulation

### Medium Priority
- [ ] Fetch MEV data from Flashbots/EigenPhi for quantification
- [ ] Gas optimization for clear() if benchmarks show issues
- [ ] Netting efficiency analysis across different pool types and volatility regimes
- [ ] Test different fee splits (70/30, 90/10) and compare LP returns

### Low Priority (Paper)
- [ ] Write Introduction and Related Work sections
- [ ] Formalize MEV elimination theorem (unified pricing proof)
- [ ] Create per-block comparison methodology diagram
- [ ] Expand simulation to 10,000+ blocks for statistical significance
- [ ] Sepolia testnet deployment
- [ ] LaTeX paper skeleton

## Completed Work

- [2026-03-31] Project design spec finalized
- [2026-03-31] Implementation plan created (10 tasks)
- [2026-03-31] Foundry project setup (forge, OpenZeppelin, MockERC20)
- [2026-03-31] FBAMM.sol core: addLiquidity, removeLiquidity, swap, clear
- [2026-03-31] 32 Solidity tests (unit, fuzz, invariant, gas, integration, cross-val)
- [2026-03-31] Fixed cross-decimal netting bug
- [2026-03-31] Backtest pipeline working end-to-end with real Uniswap V2 data
- [2026-03-31] First real backtest: ETH/USDC 2022 data shows 13% avg netting
- [2026-03-31] ZI trader simulation: 41% netting at λ=5, scales to 65% at λ=20
- [2026-03-31] CEX GBM + arbitrageur agent added
- [2026-03-31] KEY FINDING: FBAMM does not reduce LVR — arb profits same or higher
- [2026-03-31] GitHub: https://github.com/WillInvest/FBAMM.git
- [2026-03-31] Cron job: every 3h on Anthropic cloud

## Session Log

### Session 1 (2026-03-31)
- Built entire project from scratch: contract, tests, backtest, simulation
- ZI trader results: strong execution quality improvement, good netting
- Added CEX GBM + arbitrageur: discovered FBAMM doesn't reduce LVR
- **Key insight:** FBAMM's value proposition may be execution quality (unified price), not LP protection. This shapes the paper's narrative.
- **Suggestion for next session:** The LVR finding is the most important thing to investigate. Read the FM-AMM paper to understand how they handle this. Consider whether the arb's timing (seeing reserves before batch) is realistic. Try different arb orderings in the simulation.

## Open Questions
- Does FBAMM truly protect against MEV, or only against within-block price variance?
- How does FM-AMM (Canidio & Fritsch) solve the arb-in-batch problem?
- Should FBAMM use commit-reveal to hide order flow until clearing?
- Is the 80/20 fee split optimal? Does the clearing bounty need to be dynamic?
- What block range gives the best mix of high/low volatility for the paper?

## Ideas
- Commit-reveal scheme: traders submit hash of order, reveal after batch close
- Time-weighted batch clearing: weight orders by how early they were submitted
- Multi-block arb analysis: does FBAMM reduce arb profitability over multiple blocks?
- Compare FBAMM against FM-AMM (CoW AMM) directly in simulation

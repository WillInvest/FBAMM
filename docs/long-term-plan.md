# FBAMM Long-Term Plan

**Last updated:** 2026-04-02
**Objectives:**
1. Working FBAMM on Anvil testnet with backtest pipeline
2. Publication-ready academic paper

## Current Status

Phase 2: Agent simulation and analysis. Core contract built. ZI trader + arbitrageur + CEX (GBM) simulation running. First results show an unexpected finding that needs investigation.

## IMPORTANT FINDINGS

### Finding 1 (2026-03-31): FBAMM does NOT reduce LVR
**FBAMM does NOT reduce arbitrageur profits (LVR) vs UniswapV2.** In all tested configurations, the arb extracts MORE from FBAMM than UniV2.

### Finding 2 (2026-04-02): Root cause confirmed — sensitivity analysis complete

**Sensitivity analysis (5×5 parameter grid, 5 seeds, 1000 blocks each) reveals a clear pattern:**

Arb profit ratio (FBAMM / UniV2):
```
σ \ λ     λ=1    λ=3    λ=5   λ=10   λ=20
σ=0.005   1.22   1.33   1.51   1.58   1.64
σ=0.010   1.07   1.21   1.37   1.46   1.58
σ=0.020   1.03   1.10   1.19   1.27   1.43
σ=0.040   1.01   1.04   1.08   1.13   1.24
σ=0.080   1.00   1.01   1.02   1.04   1.08
```

**Key pattern**: FBAMM arb excess DECREASES with higher sigma, INCREASES with higher lambda.
- At σ≥0.04: ratio ≈ 1.0 (FBAMM ≈ UniV2 for arb)
- At σ=0.005, λ=20: ratio = 1.64 (FBAMM 64% more arb-profitable)

**Root cause (mechanistic)**: The higher FBAMM arb profit comes from HIGHER PER-BLOCK profit, NOT more arb blocks. Example at σ=0.005, λ=5:
- Block counts: UniV2=861 vs FBAMM=875 (similar)
- Per-block profit: UniV2=$31 vs FBAMM=$47 (48% more!)
- Average gap sizes are IDENTICAL

The batch clearing mechanism gives the arb favorable netting against ZI sellers: the arb buys ZI sellers' ETH at the clearing price with zero additional price impact. This is pure "execution efficiency" that benefits the arb. At low sigma, small ZI flows are large relative to CEX moves, so netting gains dominate.

**LP PnL decomposition** (σ=0.02, λ=5, 2000 blocks):
- Total LP gap (FBAMM − UniV2): −$41,843
  - (A) Lower fee revenue to LP (80% vs 100%): −$21,090 (~50% of gap)
  - (B) Higher arb-driven IL: −$20,754 (~50% of gap)

**FBAMM's confirmed advantage**: Execution quality (unified price, zero within-block spread) remains real and uncontested. Netting ratio 25-60% depending on λ.

**FBAMM's confirmed disadvantage**: Higher LVR (arb profits) AND lower LP fee share. Both hurt LPs.

## Priority Backlog

### Critical (Design Improvements Based on Findings)
- [x] ~~Analyze WHY FBAMM arb profits are higher — is this a simulation artifact or real?~~ **DONE: Real, from netting efficiency**
- [x] ~~Run sensitivity analysis: vary sigma, arrival_rate~~ **DONE: Clear sigma/lambda pattern found**
- [ ] Implement commit-reveal arb model: arb must submit BEFORE observing batch order book
- [ ] Re-read Canidio & Fritsch (2023) FM-AMM paper — do they address the netting-arb benefit?
- [ ] Test modified fee split (90/10, 95/5) to see when LP returns become competitive with UniV2
- [ ] Simulate "arb-blind" scenario: arb cannot see reserves during batch (only last clear price)

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
- [2026-04-02] Sensitivity analysis: 5×5 sigma/lambda grid, 5 seeds, 1000 blocks = 125 simulations
- [2026-04-02] Root cause analysis: FBAMM arb advantage = netting efficiency (higher per-block profit)
- [2026-04-02] LP PnL decomposition: ~50% from lower fee share, ~50% from higher arb-driven IL
- [2026-04-02] Key insight: FBAMM is approximately equivalent to UniV2 at high volatility (σ≥0.04)

## Session Log

### Session 2 (2026-04-02)
- **Task**: Root cause analysis of FBAMM's higher arb profits (key unresolved question from Session 1)
- Wrote `sensitivity.py`: 5×5 grid over sigma × lambda, 5 seeds each, 1000 blocks = 125 simulations
- Wrote `diagnose_arb.py`: per-block decomposition to isolate mechanism
- **Key finding**: FBAMM arb advantage comes from HIGHER PER-BLOCK profit via netting efficiency
  - Arb buys ZI sellers' ETH at clearing price with zero additional price impact
  - Effect scales: stronger at low sigma (ZI noise dominates CEX moves), high lambda (more sellers)
  - At σ≥0.04 (high volatility), ratio ≈ 1.0 → FBAMM and UniV2 are equivalent for LPs
- **LP decomposition**: gap is ~50% lower fee share + ~50% higher arb-driven IL
- **Suggestion for next session**: Implement commit-reveal arb model where arb uses LAST BATCH price
  (not live reserves) to compute its trade. This eliminates the informational advantage and tests
  whether FBAMM can be designed to actually protect against LVR. Compare LP returns with revised model.

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

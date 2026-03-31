# FBAMM System Design Spec

**Date:** 2026-03-31
**Status:** Draft
**Objective:** Build, test, and evaluate a Frequent Batch Auction AMM that eliminates MEV and improves capital efficiency compared to Uniswap V2, producing a publication-ready academic paper.

---

## 1. Overview

FBAMM extends the traditional constant-product AMM (Uniswap V2) by introducing a batch clearing mechanism. Instead of executing swaps immediately against LP reserves, trades accumulate in per-block batches. A clearing step nets buy and sell orders against each other, and only the net imbalance interacts with the LP reserves. All participants in a batch receive a unified price, eliminating frontrunning and sandwich attacks.

### Two End-Goal Objectives

1. **Working system** — FBAMM deployed on Anvil local testnet with agent-driven interaction, backtesting against real Uniswap V2 transactions, and a full analysis pipeline.
2. **Academic paper** — Publication-ready paper with rigorous experimental methodology, comprehensive results, plots, and diagrams comparing FBAMM to Uniswap V2.

---

## 2. Smart Contract — `FBAMM.sol`

A single monolithic Solidity contract using Foundry. Designed for simplicity first; modular extraction (separate pool, batch engine, fee vault, router, factory) planned for a later phase.

### 2.1 State Variables

| Variable | Type | Description |
|----------|------|-------------|
| `token0`, `token1` | `address` | The two ERC-20 tokens in the pair |
| `reserve0`, `reserve1` | `uint256` | LP reserves (constant product: `k = reserve0 * reserve1`) |
| `Qb` | `uint256` | Buy accumulator — total token1 deposited by buyers this batch |
| `Qs` | `uint256` | Sell accumulator — total token0 deposited by sellers this batch |
| `pendingFees` | `uint256` | Fees collected this batch, not yet distributed |
| `lastClearedBlock` | `uint256` | Block number of last clearing (prevents double-clear) |
| `batchBuyOrders` | `mapping(address => uint256)` | Per-address buy amounts in current batch |
| `batchSellOrders` | `mapping(address => uint256)` | Per-address sell amounts in current batch |
| `batchBuyers` | `address[]` | List of buyers in current batch (for iteration during clearing) |
| `batchSellers` | `address[]` | List of sellers in current batch (for iteration during clearing) |
| `totalSupply`, `balanceOf` | ERC-20 | LP token for liquidity providers |

### 2.2 Functions

#### `addLiquidity(uint256 amount0, uint256 amount1) → uint256 lpTokens`
- Transfers `amount0` of token0 and `amount1` of token1 from caller
- Mints LP tokens proportional to the share of reserves added
- First depositor sets the initial ratio; subsequent deposits must match the current ratio
- Updates `reserve0`, `reserve1`

#### `removeLiquidity(uint256 lpAmount) → (uint256 amount0, uint256 amount1)`
- Burns `lpAmount` of LP tokens
- Returns proportional share of `reserve0` and `reserve1`
- Updates reserves

#### `swap(address tokenIn, uint256 amountIn)`
- Transfers `amountIn` of `tokenIn` from caller
- Deducts 0.3% fee → added to `pendingFees`
- Remaining amount added to `Qb` (if buying token0) or `Qs` (if buying token1)
- Records the caller's order in `batchBuyOrders` or `batchSellOrders`
- Appends caller to `batchBuyers` or `batchSellers`
- Does NOT execute the trade — just queues it

#### `clear()`
- Reverts if `lastClearedBlock == block.number` (one clearing per block)
- **Step 1 — Netting:** `netted = min(Qb, Qs)`. This amount is matched peer-to-peer at a unified price without touching reserves.
- **Step 2 — Net demand:** `netDemand = |Qb - Qs|`. This amount goes through the constant-product curve: `amountOut = (netDemand * reserveOut) / (reserveIn + netDemand)`. Reserves are updated.
- **Step 3 — Unified price:** Calculate the single execution price for this batch. All participants get the same price regardless of submission order.
- **Step 4 — Distribution:** Iterate through `batchBuyers` and `batchSellers`, distribute output tokens proportional to each participant's order size.
- **Step 5 — Fees:** `pendingFees * 80%` added to reserves (benefits LPs by increasing `k`). `pendingFees * 20%` transferred to `msg.sender` (the clearing bounty).
- **Step 6 — Reset:** Clear `Qb`, `Qs`, `pendingFees`, `batchBuyOrders`, `batchSellOrders`, `batchBuyers`, `batchSellers`. Set `lastClearedBlock = block.number`.

### 2.3 Fee Structure

- **Trade fee:** 0.3% of every swap amount (same as Uniswap V2)
- **LP share:** 80% of fees → added to reserves during clearing
- **Clearing bounty:** 20% of fees → paid to whoever calls `clear()`
- **Design note:** The clearing bounty mechanism is intentionally simple (Approach A). The interface is designed so it can be upgraded to an auction-based mechanism (Approach C) later without changing the core swap/clearing logic.

### 2.4 Constant-Product Formula

Same as Uniswap V2 for the net demand portion:
```
x * y = k
amountOut = (amountIn * reserveOut) / (reserveIn + amountIn)
```

Only the net imbalance after netting touches this formula. The netted portion is pure peer-to-peer exchange at the unified price.

---

## 3. Test Suite (Foundry)

### 3.1 Unit Tests
- `addLiquidity`: correct LP token minting, ratio enforcement, first deposit
- `removeLiquidity`: correct proportional returns, LP token burning
- `swap`: correct fee deduction, accumulator updates, order recording
- `clear`: correct netting, reserve updates, price calculation, distribution, fee split, bounty payment
- `clear` revert: double-clear in same block

### 3.2 Fuzz Tests
- Random swap amounts across both directions
- Random sequences of swaps followed by clearing
- Random liquidity additions/removals interleaved with swaps

### 3.3 Invariant Tests
- `k` never decreases after clearing (fees increase `k`)
- All batch participants receive the same execution price
- Total tokens in = total tokens out (conservation)
- LP token supply matches actual depositors

### 3.4 Gas Benchmarks
- Compare gas cost: FBAMM `swap` + `clear` vs Uniswap V2 `swap`
- Measure `clear()` gas scaling with number of participants in batch

---

## 4. Backtesting Methodology

### 4.1 Approach: Per-Block Isolated Comparison (Method 3)

The gold standard for fair comparison. For each block:

1. **Fork mainnet** at the target block using Anvil (`anvil --fork-url <rpc> --fork-block-number <N>`)
2. **Read real Uniswap V2 state** — get actual `reserve0`, `reserve1` from the on-chain pool at that block
3. **Deploy FBAMM** with identical initial reserves
4. **Read real Uniswap V2 results** — actual execution prices, sandwich profits, and LP state changes are ground truth from on-chain data (no simulation needed for the Uniswap V2 side)
5. **Replay swap intents** through FBAMM — same direction and amount as the real transactions
6. **Call `clear()`** on FBAMM
7. **Record metrics** for both systems at this block
8. **Discard** — move to next block

This isolates exactly one variable (the clearing mechanism) while keeping reserves, trade intents, and market conditions identical. No butterfly effect, no reserve divergence.

### 4.2 Target Pools

**Major pools (required):**
- ETH/USDC
- ETH/USDT
- ETH/WBTC

**High-MEV pools (selected by data):**
- 2-3 additional pairs chosen based on highest recorded MEV extraction in the test period
- Selection criteria: sandwich attack frequency, frontrunning volume

### 4.3 Test Period

- Start with a 1000-block sample for development and validation
- Expand to larger samples (10,000+ blocks) for paper results
- Include both high-volatility and low-volatility periods for robustness

### 4.4 Data Collection

For each block, record:

**Uniswap V2 (ground truth from chain):**
- Each swap's execution price
- Reserve state before/after block
- Fees collected

**FBAMM (simulated):**
- Unified batch price
- Netting ratio (`min(Qb, Qs) / max(Qb, Qs)`) — how much was peer-to-peer matched
- Reserve state after clearing
- Fees collected and bounty paid
- Gas cost of `clear()`

---

## 5. Comparison Metrics

### 5.1 MEV Elimination (Theoretical + Quantified)

MEV elimination is a **design property**, not an empirical finding. FBAMM enforces a unified price for all trades within a batch — there is no ordering advantage, so riskless sandwich attacks are impossible by construction. This is stated and proven as a theorem in the paper.

To **quantify the value** of this property, we cite external MEV datasets (Flashbots MEV-Explore, EigenPhi) to report how much sandwich MEV was extracted on Uniswap V2 during our test period. This gives the headline number: "FBAMM eliminates $X of MEV by design." No simulation or detection logic needed — the external dataset provides the Uniswap V2 number, and the theoretical proof provides the FBAMM number (zero).

### 5.2 Trader Execution Quality (Primary Empirical Focus)

This is where the simulation produces novel results:

- **Uniswap V2:** Each trade executes at a different price depending on ordering within the block. Earlier trades get better prices; sandwich victims get worse prices.
- **FBAMM:** All trades in a batch get the same unified price after netting.
- **Metrics:**
  - `price_improvement = (UniV2_avg_price - FBAMM_price) / UniV2_avg_price` per block, aggregated
  - Slippage comparison — how far each price deviates from the "fair" mid-market price
  - Price variance within a block: Uniswap V2 has variance (each trade moves the price), FBAMM has zero variance (unified price)
  - Worst-case execution: compare the worst price any trader gets in Uniswap V2 vs FBAMM

### 5.3 LP Returns (Primary Empirical Focus)

- **Uniswap V2:** Fee income (0.3%) minus impermanent loss over test period
- **FBAMM:** Fee income (80% of 0.3% = 0.24%) minus impermanent loss
- **Key hypothesis:** FBAMM LPs earn a lower fee rate (0.24% vs 0.3%) but suffer significantly less impermanent loss because netting reduces unnecessary reserve movement. Net LP PnL may be higher despite the lower fee share.
- **Metrics:**
  - Net LP PnL comparison (fee income - IL)
  - Impermanent loss per block
  - Reserve movement: total `|Δreserve|` per block (FBAMM should be lower due to netting)
  - Netting efficiency by pool and volatility regime

---

## 6. Reporting & Academic Paper

### 6.1 Automated Analysis Pipeline

- Python scripts (matplotlib/plotly) for plot generation
- Run after each backtest to produce:
  - Execution quality: price improvement distribution (histogram), within-block price variance comparison, worst-case execution comparison
  - LP analysis: net PnL curves over time, impermanent loss comparison, reserve movement comparison
  - Netting efficiency: netting ratio by pool and volatility regime
  - Gas cost: `clear()` cost scaling with batch size
  - MEV context: total Uniswap V2 MEV from external datasets (headline number)

### 6.2 Paper Structure

1. **Abstract**
2. **Introduction** — MEV problem in AMMs, motivation for batch auctions
3. **Related Work** — Uniswap V2/V3, CrocSwap, CoW Protocol, MEV research (Flashbots, etc.)
4. **FBAMM Mechanism** — Formal description, state variables, clearing algorithm, fee structure
5. **Implementation** — Solidity contract, Foundry test suite, design decisions
6. **Experimental Setup** — Per-block isolation methodology, target pools, data collection
7. **Results** — MEV elimination theorem, execution quality analysis, LP return analysis, gas overhead
8. **Discussion** — Limitations, edge cases (low-liquidity, single-trader blocks), gas overhead tradeoffs
9. **Conclusion & Future Work** — Auction-based clearing, multi-pool routing, mainnet deployment considerations

### 6.3 Diagrams

Build on existing HTML diagrams in `diagrams/`:
- FBAMM mechanism overview (exists: `01-fbamm-mechanism-overview.html`)
- Clearing process flow (exists: `02-clearing-process-flow.html`)
- New: Per-block comparison methodology diagram
- New: Results visualization (generated from data)

---

## 7. Autonomous Development Loop

### 7.1 Per-Session Loop

Each development session (manual or cron-triggered) follows this cycle:

1. **Read context** — `docs/long-term-plan.md`, recent git log, progress notes
2. **Brainstorm** — Assess current state, identify highest priority work, potentially add new ideas (new pools, better plots, methodology improvements)
3. **Plan** — Define specific deliverables for this session
4. **Implement + Test** — Write code, run tests, fix failures
5. **Review** — Verify work, run analysis if applicable
6. **Commit** — Clear commit messages documenting what was done and why
7. **Update long-term plan** — Mark completed items, add new discoveries, leave suggestion for next session
8. **Push** — Push to remote for next session to pick up

### 7.2 Long-Term Plan Document

Living document at `docs/long-term-plan.md` containing:
- Overall objectives and success criteria
- Prioritized task backlog (ordered by impact)
- Completed work log with dates and commit references
- Suggestions from each session for the next
- Open questions, ideas, and experimental hypotheses

### 7.3 Cron Agent Setup

After the foundation is laid (contract, tests, replay harness):
- Scheduled via Claude Code's native remote trigger system
- Runs on a regular interval (e.g., every 2-4 hours)
- Each run is an autonomous session following the loop above
- Environment: to be decided (Stevens blockchain bridge or Anthropic cloud)

### 7.4 Key Principle

Each session thinks independently. The previous session's suggestion is input, not instruction. The current session can disagree, reprioritize, or take a completely different direction based on what it observes.

---

## 8. Technology Stack

| Component | Technology |
|-----------|-----------|
| Smart contracts | Solidity (latest stable), Foundry (forge, anvil, cast) |
| Local testnet | Anvil (Foundry) with mainnet fork |
| On-chain data | Cast + RPC provider (Alchemy/Infura) for reading Uniswap V2 state and transactions |
| Analysis | Python 3, matplotlib/plotly, pandas |
| Paper | LaTeX or Markdown → PDF |
| Version control | Git with clear commit messages |
| CI/Scheduling | Claude Code remote triggers (cron) |

---

## 9. Out of Scope (First Phase)

- Multi-pool routing / aggregation
- Uniswap V3 concentrated liquidity comparison
- Auction-based clearing mechanism (planned for later upgrade)
- Flash loan integration
- Governance token
- Mainnet deployment (decided after Anvil + Sepolia validation)
- Formal verification (may be added for paper)
- Upgradeable proxy pattern

---

## 10. Risk & Mitigation

| Risk | Mitigation |
|------|-----------|
| `clear()` gas too expensive with many participants | Gas benchmarks early; batch size limits if needed |
| Low netting ratio (one-sided blocks) | Expected in some blocks — report netting distribution honestly |
| RPC rate limits during fork replay | Use local archive node or batched requests with backoff |
| Reserve divergence concern | Method 3 (per-block isolation) eliminates this entirely |
| Single-trader blocks (no netting possible) | Report these as a known limitation; FBAMM still provides unified price |

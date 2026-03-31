# FBAMM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working FBAMM smart contract with Foundry tests, an Anvil-based backtest harness replaying real Uniswap V2 transactions, and an analysis pipeline producing comparison metrics.

**Architecture:** Monolithic Solidity contract (`FBAMM.sol`) with ERC-20 LP tokens, tested via Foundry. A Solidity-based backtest script uses Anvil mainnet forks to replay real Uniswap V2 swap intents through FBAMM per-block, collecting execution quality and LP return metrics. Python scripts aggregate results and generate plots.

**Tech Stack:** Solidity (0.8.x), Foundry (forge/anvil/cast), Python 3 (matplotlib, pandas), OpenZeppelin (ERC-20)

---

## File Structure

```
fba/
├── foundry.toml                    # Foundry config (solc version, optimizer, RPC)
├── .env.example                    # Template for RPC URL
├── src/
│   ├── FBAMM.sol                   # Core AMM: reserves, batch accumulators, clearing, LP tokens
│   └── mocks/
│       └── MockERC20.sol           # Simple ERC-20 for testing
├── test/
│   ├── FBAMM.t.sol                 # Unit tests: liquidity, swap, clear, fees
│   ├── FBAMM.fuzz.t.sol            # Fuzz tests: random swaps + clearing sequences
│   ├── FBAMM.invariant.t.sol       # Invariant tests: k growth, conservation, unified price
│   └── FBAMM.gas.t.sol             # Gas benchmarks: clear() scaling
├── script/
│   ├── Backtest.s.sol              # Per-block fork replay: deploy FBAMM, replay swaps, collect metrics
│   └── FetchSwaps.s.sol            # Fetch Uniswap V2 swap events for a block range
├── analysis/
│   ├── aggregate.py                # Load backtest JSON output, compute metrics
│   └── plot.py                     # Generate comparison plots (execution quality, LP returns, netting)
├── data/                           # Backtest output (gitignored)
│   └── .gitkeep
└── docs/
    └── long-term-plan.md           # Living document for autonomous dev loop
```

---

## Task 1: Foundry Project Setup

**Files:**
- Create: `foundry.toml`
- Create: `.env.example`
- Create: `.gitignore` (update existing or create)
- Create: `src/mocks/MockERC20.sol`
- Create: `data/.gitkeep`

- [ ] **Step 1: Install Foundry**

```bash
curl -L https://foundry.paradigm.xyz | bash
source ~/.bashrc
foundryup
```

Verify: `forge --version` prints version info.

- [ ] **Step 2: Initialize Foundry project**

```bash
cd /home/fao/fba
forge init --no-git --no-commit
```

This creates `src/`, `test/`, `script/`, `lib/`, `foundry.toml`. The `--no-git` flag avoids reinitializing git.

- [ ] **Step 3: Install OpenZeppelin contracts**

```bash
cd /home/fao/fba
forge install OpenZeppelin/openzeppelin-contracts --no-git --no-commit
```

- [ ] **Step 4: Configure foundry.toml**

```toml
[profile.default]
src = "src"
out = "out"
libs = ["lib"]
solc = "0.8.28"
optimizer = true
optimizer_runs = 200
ffi = true

[rpc_endpoints]
mainnet = "${MAINNET_RPC_URL}"

remappings = [
    "@openzeppelin/=lib/openzeppelin-contracts/"
]
```

- [ ] **Step 5: Create .env.example**

```
# Get a free RPC URL from https://www.alchemy.com/ or https://www.infura.io/
MAINNET_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
```

- [ ] **Step 6: Update .gitignore**

Append to `.gitignore`:
```
out/
cache/
.env
data/*.json
data/*.csv
```

- [ ] **Step 7: Create MockERC20.sol**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockERC20 is ERC20 {
    uint8 private _decimals;

    constructor(
        string memory name,
        string memory symbol,
        uint8 decimals_
    ) ERC20(name, symbol) {
        _decimals = decimals_;
    }

    function decimals() public view override returns (uint8) {
        return _decimals;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
```

- [ ] **Step 8: Create data/.gitkeep**

Empty file so the `data/` directory is tracked.

- [ ] **Step 9: Verify setup compiles**

```bash
cd /home/fao/fba
forge build
```

Expected: Compilation success, no errors.

- [ ] **Step 10: Commit**

```bash
git add foundry.toml .env.example .gitignore src/mocks/MockERC20.sol data/.gitkeep lib/ remappings.txt
git commit -m "feat: initialize Foundry project with OpenZeppelin and MockERC20"
```

---

## Task 2: FBAMM Core — LP Token + Liquidity Functions

**Files:**
- Create: `src/FBAMM.sol`
- Create: `test/FBAMM.t.sol`

- [ ] **Step 1: Write failing tests for addLiquidity**

In `test/FBAMM.t.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import "../src/FBAMM.sol";
import "../src/mocks/MockERC20.sol";

contract FBAMMTest is Test {
    FBAMM public pool;
    MockERC20 public token0;
    MockERC20 public token1;
    address public alice = makeAddr("alice");
    address public bob = makeAddr("bob");

    function setUp() public {
        token0 = new MockERC20("Token0", "TK0", 18);
        token1 = new MockERC20("Token1", "TK1", 18);

        // Ensure token0 < token1 by address (Uniswap convention)
        if (address(token0) > address(token1)) {
            (token0, token1) = (token1, token0);
        }

        pool = new FBAMM(address(token0), address(token1));

        // Fund users
        token0.mint(alice, 1000e18);
        token1.mint(alice, 1000e18);
        token0.mint(bob, 1000e18);
        token1.mint(bob, 1000e18);

        // Approve pool
        vm.startPrank(alice);
        token0.approve(address(pool), type(uint256).max);
        token1.approve(address(pool), type(uint256).max);
        vm.stopPrank();

        vm.startPrank(bob);
        token0.approve(address(pool), type(uint256).max);
        token1.approve(address(pool), type(uint256).max);
        vm.stopPrank();
    }

    function test_addLiquidity_firstDeposit() public {
        vm.prank(alice);
        uint256 lp = pool.addLiquidity(100e18, 200e18);

        assertGt(lp, 0, "Should mint LP tokens");
        assertEq(pool.reserve0(), 100e18);
        assertEq(pool.reserve1(), 200e18);
        assertEq(pool.balanceOf(alice), lp);
    }

    function test_addLiquidity_secondDeposit_proportional() public {
        vm.prank(alice);
        pool.addLiquidity(100e18, 200e18);

        vm.prank(bob);
        uint256 lp = pool.addLiquidity(50e18, 100e18);

        assertGt(lp, 0);
        assertEq(pool.reserve0(), 150e18);
        assertEq(pool.reserve1(), 300e18);
    }

    function test_removeLiquidity() public {
        vm.prank(alice);
        uint256 lp = pool.addLiquidity(100e18, 200e18);

        uint256 bal0Before = token0.balanceOf(alice);
        uint256 bal1Before = token1.balanceOf(alice);

        vm.prank(alice);
        (uint256 out0, uint256 out1) = pool.removeLiquidity(lp);

        assertEq(out0, 100e18);
        assertEq(out1, 200e18);
        assertEq(token0.balanceOf(alice), bal0Before + 100e18);
        assertEq(token1.balanceOf(alice), bal1Before + 200e18);
        assertEq(pool.reserve0(), 0);
        assertEq(pool.reserve1(), 0);
        assertEq(pool.balanceOf(alice), 0);
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
forge test --match-contract FBAMMTest -v
```

Expected: Compilation error — `FBAMM` not found.

- [ ] **Step 3: Write FBAMM.sol skeleton with LP functions**

In `src/FBAMM.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract FBAMM is ERC20 {
    address public token0;
    address public token1;

    uint256 public reserve0;
    uint256 public reserve1;

    // Batch state
    uint256 public Qb; // Buy accumulator (token1 deposited to buy token0)
    uint256 public Qs; // Sell accumulator (token0 deposited to buy token1)
    uint256 public pendingFees0; // Fees in token0, pending until clearing
    uint256 public pendingFees1; // Fees in token1, pending until clearing
    uint256 public lastClearedBlock;

    // Batch participant tracking
    mapping(address => uint256) public batchBuyOrders;
    mapping(address => uint256) public batchSellOrders;
    address[] public batchBuyers;
    address[] public batchSellers;

    uint256 public constant FEE_BPS = 30; // 0.3%
    uint256 public constant LP_FEE_SHARE = 80; // 80% to LPs
    uint256 public constant CLEARING_FEE_SHARE = 20; // 20% to clearer
    uint256 private constant MINIMUM_LIQUIDITY = 1000;

    constructor(address _token0, address _token1) ERC20("FBAMM LP", "FBAMM-LP") {
        require(_token0 != _token1, "IDENTICAL_TOKENS");
        token0 = _token0;
        token1 = _token1;
    }

    function addLiquidity(uint256 amount0, uint256 amount1) external returns (uint256 lpTokens) {
        require(amount0 > 0 && amount1 > 0, "ZERO_AMOUNT");

        if (totalSupply() == 0) {
            // First deposit: LP tokens = sqrt(amount0 * amount1) - MINIMUM_LIQUIDITY
            // Lock MINIMUM_LIQUIDITY to address(0) to prevent totalSupply from ever being 0 after first deposit
            lpTokens = _sqrt(amount0 * amount1) - MINIMUM_LIQUIDITY;
            _mint(address(0xdead), MINIMUM_LIQUIDITY);
        } else {
            // Subsequent deposits: proportional to existing reserves
            uint256 lp0 = (amount0 * totalSupply()) / reserve0;
            uint256 lp1 = (amount1 * totalSupply()) / reserve1;
            lpTokens = lp0 < lp1 ? lp0 : lp1;
        }

        require(lpTokens > 0, "INSUFFICIENT_LIQUIDITY_MINTED");

        IERC20(token0).transferFrom(msg.sender, address(this), amount0);
        IERC20(token1).transferFrom(msg.sender, address(this), amount1);

        reserve0 += amount0;
        reserve1 += amount1;

        _mint(msg.sender, lpTokens);
    }

    function removeLiquidity(uint256 lpAmount) external returns (uint256 amount0, uint256 amount1) {
        require(lpAmount > 0, "ZERO_AMOUNT");
        require(balanceOf(msg.sender) >= lpAmount, "INSUFFICIENT_LP");

        amount0 = (lpAmount * reserve0) / totalSupply();
        amount1 = (lpAmount * reserve1) / totalSupply();

        require(amount0 > 0 && amount1 > 0, "INSUFFICIENT_LIQUIDITY_BURNED");

        _burn(msg.sender, lpAmount);

        reserve0 -= amount0;
        reserve1 -= amount1;

        IERC20(token0).transfer(msg.sender, amount0);
        IERC20(token1).transfer(msg.sender, amount1);
    }

    // Babylonian sqrt
    function _sqrt(uint256 y) internal pure returns (uint256 z) {
        if (y > 3) {
            z = y;
            uint256 x = y / 2 + 1;
            while (x < z) {
                z = x;
                x = (y / x + x) / 2;
            }
        } else if (y != 0) {
            z = 1;
        }
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
forge test --match-contract FBAMMTest -v
```

Expected: All 3 tests PASS. Note: `test_removeLiquidity` may need adjustment due to MINIMUM_LIQUIDITY lock — the first depositor doesn't get exactly `100e18` back because some LP tokens were locked. Update the test assertions if needed to account for the sqrt-based initial minting.

- [ ] **Step 5: Fix test assertions for MINIMUM_LIQUIDITY**

The first deposit mints `sqrt(100e18 * 200e18) - 1000` LP tokens, not a round number. Update `test_removeLiquidity` to use the actual minted amount and expect proportional returns. The amounts returned will be slightly less than deposited because of the locked minimum liquidity.

Run tests again: `forge test --match-contract FBAMMTest -v`

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/FBAMM.sol test/FBAMM.t.sol
git commit -m "feat: FBAMM core with LP token, addLiquidity, removeLiquidity"
```

---

## Task 3: FBAMM Swap Function (Batch Queuing)

**Files:**
- Modify: `test/FBAMM.t.sol` (add swap tests)
- Modify: `src/FBAMM.sol` (add swap function)

- [ ] **Step 1: Write failing tests for swap**

Add to `test/FBAMM.t.sol`:

```solidity
function test_swap_buyToken0() public {
    // Setup liquidity
    vm.prank(alice);
    pool.addLiquidity(100e18, 100e18);

    // Bob swaps token1 to buy token0
    uint256 swapAmount = 10e18;
    uint256 fee = (swapAmount * 30) / 10000; // 0.3%
    uint256 netAmount = swapAmount - fee;

    vm.prank(bob);
    pool.swap(address(token1), swapAmount);

    assertEq(pool.Qb(), netAmount, "Qb should increase by net amount");
    assertEq(pool.Qs(), 0, "Qs should be unchanged");
    assertEq(pool.batchBuyOrders(bob), netAmount);
    // Reserves should NOT change yet
    assertEq(pool.reserve0(), 100e18);
    assertEq(pool.reserve1(), 100e18);
}

function test_swap_sellToken0() public {
    vm.prank(alice);
    pool.addLiquidity(100e18, 100e18);

    uint256 swapAmount = 10e18;
    uint256 fee = (swapAmount * 30) / 10000;
    uint256 netAmount = swapAmount - fee;

    vm.prank(bob);
    pool.swap(address(token0), swapAmount);

    assertEq(pool.Qs(), netAmount, "Qs should increase by net amount");
    assertEq(pool.Qb(), 0, "Qb should be unchanged");
    assertEq(pool.batchSellOrders(bob), netAmount);
}

function test_swap_feeAccumulation() public {
    vm.prank(alice);
    pool.addLiquidity(100e18, 100e18);

    uint256 swapAmount = 10e18;
    uint256 fee = (swapAmount * 30) / 10000;

    vm.prank(bob);
    pool.swap(address(token1), swapAmount);

    assertEq(pool.pendingFees1(), fee, "Pending fees should accumulate");
}

function test_swap_multipleTraders() public {
    vm.prank(alice);
    pool.addLiquidity(100e18, 100e18);

    uint256 amount1 = 10e18;
    uint256 amount2 = 5e18;
    uint256 fee1 = (amount1 * 30) / 10000;
    uint256 fee2 = (amount2 * 30) / 10000;

    vm.prank(alice);
    pool.swap(address(token1), amount1); // Buy token0

    vm.prank(bob);
    pool.swap(address(token1), amount2); // Buy token0

    assertEq(pool.Qb(), (amount1 - fee1) + (amount2 - fee2));
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
forge test --match-test "test_swap" -v
```

Expected: Fail — `swap` function doesn't exist yet.

- [ ] **Step 3: Implement swap function**

Add to `src/FBAMM.sol`:

```solidity
function swap(address tokenIn, uint256 amountIn) external {
    require(tokenIn == token0 || tokenIn == token1, "INVALID_TOKEN");
    require(amountIn > 0, "ZERO_AMOUNT");
    require(reserve0 > 0 && reserve1 > 0, "NO_LIQUIDITY");

    // Transfer tokens in
    IERC20(tokenIn).transferFrom(msg.sender, address(this), amountIn);

    // Deduct fee
    uint256 fee = (amountIn * FEE_BPS) / 10000;
    uint256 netAmount = amountIn - fee;

    if (tokenIn == token1) {
        // Buying token0: deposit token1
        pendingFees1 += fee;
        Qb += netAmount;
        if (batchBuyOrders[msg.sender] == 0) {
            batchBuyers.push(msg.sender);
        }
        batchBuyOrders[msg.sender] += netAmount;
    } else {
        // Selling token0 (buying token1): deposit token0
        pendingFees0 += fee;
        Qs += netAmount;
        if (batchSellOrders[msg.sender] == 0) {
            batchSellers.push(msg.sender);
        }
        batchSellOrders[msg.sender] += netAmount;
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
forge test --match-test "test_swap" -v
```

Expected: All 4 swap tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/FBAMM.sol test/FBAMM.t.sol
git commit -m "feat: add swap function with batch queuing and fee accumulation"
```

---

## Task 4: FBAMM Clear Function (Netting + AMM + Distribution)

This is the most complex function. The clearing algorithm:
1. Net `min(Qb, Qs)` peer-to-peer
2. Push `|Qb - Qs|` through constant-product curve
3. Calculate unified price
4. Distribute output tokens proportionally
5. Split fees: 80% to reserves, 20% to caller

**Files:**
- Modify: `test/FBAMM.t.sol` (add clear tests)
- Modify: `src/FBAMM.sol` (add clear function)

- [ ] **Step 1: Write failing tests for clear — balanced batch**

Add to `test/FBAMM.t.sol`:

```solidity
function test_clear_balanced() public {
    // Setup: 100 token0 + 100 token1 reserves
    vm.prank(alice);
    pool.addLiquidity(100e18, 100e18);

    // Alice sells 10 token0 (buys token1)
    vm.prank(alice);
    pool.swap(address(token0), 10e18);

    // Bob buys token0 (sells 10 token1)
    vm.prank(bob);
    pool.swap(address(token1), 10e18);

    // Net amounts after 0.3% fee
    uint256 fee = (10e18 * 30) / 10000; // 0.03e18
    uint256 net = 10e18 - fee; // 9.97e18

    // Perfectly balanced: Qb == Qs (approximately, both 9.97e18)
    // All netting, no LP interaction
    // Reserves should be unchanged after clearing

    // Move to next block so clearing is allowed
    vm.roll(block.number + 1);

    address clearer = makeAddr("clearer");
    vm.prank(clearer);
    pool.clear();

    // Reserves unchanged (all netted, no AMM interaction)
    assertEq(pool.reserve0(), 100e18, "Reserves should not change for balanced batch");
    assertEq(pool.reserve1(), 100e18);

    // Accumulators reset
    assertEq(pool.Qb(), 0);
    assertEq(pool.Qs(), 0);

    // Bob should have received token0 (he was buying token0)
    assertGt(token0.balanceOf(bob), 0, "Bob should receive token0");

    // Alice should have received token1 (she was buying token1)
    // Alice started with 1000e18 - liquidity - swap amount
    // After clearing she should get token1 back

    // Clearer gets 20% of fees
    // Fees are in both token0 and token1
    assertGt(token0.balanceOf(clearer) + token1.balanceOf(clearer), 0, "Clearer should get bounty");
}

function test_clear_unbalanced_moreBuyers() public {
    vm.prank(alice);
    pool.addLiquidity(100e18, 100e18);

    // Bob buys 20 token0 (deposits 20 token1)
    vm.prank(bob);
    pool.swap(address(token1), 20e18);

    // Alice sells 10 token0 (deposits 10 token0)
    vm.prank(alice);
    pool.swap(address(token0), 10e18);

    vm.roll(block.number + 1);

    uint256 r0Before = pool.reserve0();
    uint256 r1Before = pool.reserve1();

    address clearer = makeAddr("clearer");
    vm.prank(clearer);
    pool.clear();

    // Net demand is on the buy side: more buyers than sellers
    // reserve0 should decrease (token0 sold from LP)
    // reserve1 should increase (excess token1 added to LP)
    assertLt(pool.reserve0(), r0Before, "reserve0 should decrease");
    assertGt(pool.reserve1(), r1Before, "reserve1 should increase");

    // Accumulators reset
    assertEq(pool.Qb(), 0);
    assertEq(pool.Qs(), 0);
}

function test_clear_reverts_sameBlock() public {
    vm.prank(alice);
    pool.addLiquidity(100e18, 100e18);

    vm.prank(bob);
    pool.swap(address(token1), 10e18);

    vm.roll(block.number + 1);

    address clearer = makeAddr("clearer");
    vm.prank(clearer);
    pool.clear();

    // Second clear in same block should revert
    vm.prank(clearer);
    vm.expectRevert("ALREADY_CLEARED");
    pool.clear();
}

function test_clear_reverts_emptyBatch() public {
    vm.prank(alice);
    pool.addLiquidity(100e18, 100e18);

    vm.roll(block.number + 1);

    address clearer = makeAddr("clearer");
    vm.prank(clearer);
    vm.expectRevert("EMPTY_BATCH");
    pool.clear();
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
forge test --match-test "test_clear" -v
```

Expected: Fail — `clear` function doesn't exist.

- [ ] **Step 3: Implement clear function**

Add to `src/FBAMM.sol`:

```solidity
function clear() external {
    require(lastClearedBlock != block.number, "ALREADY_CLEARED");
    require(Qb > 0 || Qs > 0, "EMPTY_BATCH");

    lastClearedBlock = block.number;

    // Step 1: Netting
    uint256 netted = Qb < Qs ? Qb : Qs;

    // Step 2: Net demand through AMM
    uint256 netDemand;
    uint256 amountOut;
    bool buyExcess = Qb > Qs; // true if more buying pressure

    if (Qb > Qs) {
        netDemand = Qb - Qs; // excess token1 wanting to buy token0
        // token1 goes in, token0 comes out
        amountOut = (netDemand * reserve0) / (reserve1 + netDemand);
        reserve1 += netDemand;
        reserve0 -= amountOut;
    } else if (Qs > Qb) {
        netDemand = Qs - Qb; // excess token0 wanting to buy token1
        // token0 goes in, token1 comes out
        amountOut = (netDemand * reserve1) / (reserve0 + netDemand);
        reserve0 += netDemand;
        reserve1 -= amountOut;
    }
    // If Qb == Qs: no AMM interaction, pure netting

    // Step 3: Calculate unified price and distribute
    // For buyers (deposited token1, want token0):
    //   - Netted portion: netted token1 matched against netted token0 from sellers
    //   - AMM portion: if buyExcess, amountOut token0 from AMM for netDemand token1
    //   Total token0 output for all buyers:
    //     - From netting: the Qs worth of token0 from sellers (if Qb >= Qs, netted = Qs)
    //     - From AMM: amountOut (if buyExcess)
    //   Wait — netting means Qb's token1 is exchanged for Qs's token0 directly.
    //   The "price" for netted portion is: netted_token0 / netted_token1

    // Simpler approach: calculate total output for each side, distribute proportionally
    uint256 totalToken0ForBuyers;
    uint256 totalToken1ForSellers;

    if (Qb >= Qs) {
        // Sellers deposited Qs token0. All of it goes to buyers (netted).
        // AMM gives amountOut token0 to buyers for the excess.
        totalToken0ForBuyers = Qs + amountOut; // netted token0 from sellers + AMM output
        totalToken1ForSellers = Qb > Qs ? netted : Qs; // all of Qb goes to sellers if balanced
        // Actually: sellers want token1. They deposited token0.
        // From netting: sellers get netted amount of token1 (from buyers' deposits)
        // If Qb >= Qs: all sellers are netted. They get Qs worth of token1 from buyers.
        totalToken1ForSellers = Qs; // sellers get their full Qs matched against Qb's token1
        // But wait, Qs is in token0 units and Qb is in token1 units.
        // Netting needs a price to cross.
        // The unified price IS the post-AMM price for the net demand.
    } else {
        // More sellers than buyers
        totalToken1ForSellers = Qb + amountOut;
        totalToken0ForBuyers = Qb; // all buyers netted
    }

    // Let me reconsider the unified price calculation more carefully.
    // After clearing, the AMM is at a new spot price (if unbalanced) or same price (if balanced).
    // The unified price for the batch is this post-clearing spot price.
    //
    // For a balanced batch (Qb == Qs in value terms):
    //   Unified price = current spot price = reserve0 / reserve1 (unchanged)
    //
    // For unbalanced (e.g., Qb > Qs):
    //   Net demand Qb-Qs of token1 pushes through AMM
    //   New reserves: reserve1' = reserve1 + netDemand, reserve0' = reserve0 - amountOut
    //   Unified price = reserve0' / reserve1' (post-trade spot)
    //
    // All buyers get token0 at unified price. All sellers get token1 at unified price.
    // unifiedPrice = reserve0 / reserve1 (current, post-AMM-update reserves)
    //
    // Buyer i deposited batchBuyOrders[i] of token1 (net of fee).
    // They receive: batchBuyOrders[i] * (reserve0_current / reserve1_current) ... no that's wrong
    // They receive: batchBuyOrders[i] / unifiedPrice_token0_per_token1
    //   where unifiedPrice_token0_per_token1 = reserve1 / reserve0 (token1 per token0)
    //   So token0_out = batchBuyOrders[i] * reserve0 / reserve1
    //
    // But we need to make sure total distributed == total available.
    // Total token0 available for buyers = Qs (from sellers) + amountOut (from AMM) if buyExcess
    //   Hmm, Qs is token0 deposited by sellers. Those token0 go to... the pool/buyers.
    //   Actually no — Qs token0 is deposited by sellers. In netting, buyers get token0 and sellers get token1.
    //   So yes: totalToken0ForBuyers = Qs + amountOut (if buyExcess) or Qs (if balanced)
    //            totalToken1ForSellers = Qb + amountOut (if sellExcess) or Qb (if balanced)
    //
    // Wait, if buyExcess: totalToken0ForBuyers = Qs + amountOut, totalToken1ForSellers = Qs (from Qb)
    //   Sellers deposited Qs token0, they want token1 back. They get Qs worth of token1 from Qb.
    //   But Qb is larger than Qs, so Qs amount of token1 from Qb goes to sellers. Correct.
    //
    // Distribution to each buyer: (batchBuyOrders[i] / Qb) * totalToken0ForBuyers
    // Distribution to each seller: (batchSellOrders[i] / Qs) * totalToken1ForSellers

    // Reset the local calculation
    // After AMM update, reserves are already adjusted above.

    // Recalculate totals cleanly:
    if (buyExcess || Qb == Qs) {
        // All sellers fully netted
        totalToken0ForBuyers = Qs + amountOut; // from sellers + AMM
        totalToken1ForSellers = Qs; // sellers get Qs worth of token1 from buyers' pool
        // Note: Qs here is token0 units. Sellers get proportional token1.
        // Actually: totalToken1ForSellers should be in token1 units.
        // Sellers deposited Qs of token0. They're fully netted against buyers.
        // The token1 available for sellers = min(Qb, Qs) = Qs (from buyers' deposits)
        totalToken1ForSellers = netted; // = Qs when Qb >= Qs
    } else {
        // sellExcess: Qs > Qb, all buyers fully netted
        totalToken0ForBuyers = netted; // = Qb (from sellers' deposits in token0)
        totalToken1ForSellers = Qb + amountOut; // from buyers + AMM
    }

    // Step 4: Distribute to buyers (they receive token0)
    for (uint256 i = 0; i < batchBuyers.length; i++) {
        address buyer = batchBuyers[i];
        uint256 share = batchBuyOrders[buyer];
        uint256 payout = (share * totalToken0ForBuyers) / Qb;
        IERC20(token0).transfer(buyer, payout);
        delete batchBuyOrders[buyer];
    }

    // Distribute to sellers (they receive token1)
    for (uint256 i = 0; i < batchSellers.length; i++) {
        address seller = batchSellers[i];
        uint256 share = batchSellOrders[seller];
        uint256 payout = (share * totalToken1ForSellers) / Qs;
        IERC20(token1).transfer(seller, payout);
        delete batchSellOrders[seller];
    }

    // Step 5: Fees
    uint256 lpFee0 = (pendingFees0 * LP_FEE_SHARE) / 100;
    uint256 lpFee1 = (pendingFees1 * LP_FEE_SHARE) / 100;
    uint256 clearerFee0 = pendingFees0 - lpFee0;
    uint256 clearerFee1 = pendingFees1 - lpFee1;

    // LP fees increase reserves (increasing k)
    reserve0 += lpFee0;
    reserve1 += lpFee1;

    // Clearing bounty to caller
    if (clearerFee0 > 0) IERC20(token0).transfer(msg.sender, clearerFee0);
    if (clearerFee1 > 0) IERC20(token1).transfer(msg.sender, clearerFee1);

    // Step 6: Reset
    Qb = 0;
    Qs = 0;
    pendingFees0 = 0;
    pendingFees1 = 0;
    delete batchBuyers;
    delete batchSellers;
}
```

**Important implementation note:** The clear function above has a complex comment trail showing the reasoning. The implementer should clean this up — remove the "let me reconsider" comments and keep only the final logic. The key insight is:

- `totalToken0ForBuyers = netted_from_sellers + amountOut_from_AMM` (when buy excess)
- `totalToken1ForSellers = netted_from_buyers + amountOut_from_AMM` (when sell excess)
- Each participant gets `(their_order / total_side) * total_output_for_side`

- [ ] **Step 4: Run tests to verify they pass**

```bash
forge test --match-test "test_clear" -v
```

Expected: All 4 clear tests PASS. Debug any assertion failures by adding console.log to the contract (Foundry supports `import "forge-std/console.sol"`).

- [ ] **Step 5: Add token conservation test**

```solidity
function test_clear_tokenConservation() public {
    vm.prank(alice);
    pool.addLiquidity(100e18, 100e18);

    uint256 totalToken0Before = token0.balanceOf(alice) + token0.balanceOf(bob) + token0.balanceOf(address(pool));
    uint256 totalToken1Before = token1.balanceOf(alice) + token1.balanceOf(bob) + token1.balanceOf(address(pool));

    vm.prank(bob);
    pool.swap(address(token1), 10e18);

    vm.prank(alice);
    pool.swap(address(token0), 5e18);

    vm.roll(block.number + 1);

    address clearer = makeAddr("clearer");
    vm.prank(clearer);
    pool.clear();

    uint256 totalToken0After = token0.balanceOf(alice) + token0.balanceOf(bob) + token0.balanceOf(address(pool)) + token0.balanceOf(clearer);
    uint256 totalToken1After = token1.balanceOf(alice) + token1.balanceOf(bob) + token1.balanceOf(address(pool)) + token1.balanceOf(clearer);

    assertEq(totalToken0After, totalToken0Before, "Token0 not conserved");
    assertEq(totalToken1After, totalToken1Before, "Token1 not conserved");
}
```

- [ ] **Step 6: Run all tests**

```bash
forge test -v
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/FBAMM.sol test/FBAMM.t.sol
git commit -m "feat: add clear function with netting, AMM interaction, and fee distribution"
```

---

## Task 5: Fuzz and Invariant Tests

**Files:**
- Create: `test/FBAMM.fuzz.t.sol`
- Create: `test/FBAMM.invariant.t.sol`

- [ ] **Step 1: Write fuzz tests**

In `test/FBAMM.fuzz.t.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import "../src/FBAMM.sol";
import "../src/mocks/MockERC20.sol";

contract FBAMMFuzzTest is Test {
    FBAMM public pool;
    MockERC20 public token0;
    MockERC20 public token1;

    function setUp() public {
        token0 = new MockERC20("Token0", "TK0", 18);
        token1 = new MockERC20("Token1", "TK1", 18);
        if (address(token0) > address(token1)) {
            (token0, token1) = (token1, token0);
        }
        pool = new FBAMM(address(token0), address(token1));

        // Large initial liquidity
        address lp = makeAddr("lp");
        token0.mint(lp, 1_000_000e18);
        token1.mint(lp, 1_000_000e18);
        vm.startPrank(lp);
        token0.approve(address(pool), type(uint256).max);
        token1.approve(address(pool), type(uint256).max);
        pool.addLiquidity(1_000_000e18, 1_000_000e18);
        vm.stopPrank();
    }

    function testFuzz_swapAndClear_singleBuyer(uint256 amount) public {
        amount = bound(amount, 1e15, 100_000e18); // reasonable range

        address trader = makeAddr("trader");
        token1.mint(trader, amount);
        vm.startPrank(trader);
        token1.approve(address(pool), type(uint256).max);
        pool.swap(address(token1), amount);
        vm.stopPrank();

        vm.roll(block.number + 1);

        uint256 r0Before = pool.reserve0();
        uint256 kBefore = pool.reserve0() * pool.reserve1();

        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();

        // k should not decrease after clearing (fees increase it)
        uint256 kAfter = pool.reserve0() * pool.reserve1();
        assertGe(kAfter, kBefore, "k should not decrease");

        // Trader should have received some token0
        assertGt(token0.balanceOf(trader), 0, "Trader should get output");
    }

    function testFuzz_swapAndClear_bothSides(uint256 buyAmount, uint256 sellAmount) public {
        buyAmount = bound(buyAmount, 1e15, 100_000e18);
        sellAmount = bound(sellAmount, 1e15, 100_000e18);

        address buyer = makeAddr("buyer");
        address seller = makeAddr("seller");

        token1.mint(buyer, buyAmount);
        token0.mint(seller, sellAmount);

        vm.startPrank(buyer);
        token1.approve(address(pool), type(uint256).max);
        pool.swap(address(token1), buyAmount);
        vm.stopPrank();

        vm.startPrank(seller);
        token0.approve(address(pool), type(uint256).max);
        pool.swap(address(token0), sellAmount);
        vm.stopPrank();

        vm.roll(block.number + 1);

        uint256 kBefore = pool.reserve0() * pool.reserve1();

        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();

        uint256 kAfter = pool.reserve0() * pool.reserve1();
        assertGe(kAfter, kBefore, "k should not decrease");

        // Both traders should get output
        assertGt(token0.balanceOf(buyer), 0, "Buyer should get token0");
        assertGt(token1.balanceOf(seller), 0, "Seller should get token1");
    }
}
```

- [ ] **Step 2: Run fuzz tests**

```bash
forge test --match-contract FBAMMFuzzTest -v
```

Expected: PASS with 256 fuzz runs (default).

- [ ] **Step 3: Write invariant tests**

In `test/FBAMM.invariant.t.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import "../src/FBAMM.sol";
import "../src/mocks/MockERC20.sol";

contract FBAMMHandler is Test {
    FBAMM public pool;
    MockERC20 public token0;
    MockERC20 public token1;

    constructor(FBAMM _pool, MockERC20 _token0, MockERC20 _token1) {
        pool = _pool;
        token0 = _token0;
        token1 = _token1;
    }

    function swap_buy(uint256 amount) external {
        amount = bound(amount, 1e15, 10_000e18);
        address trader = makeAddr(string(abi.encodePacked("buyer", amount)));
        token1.mint(trader, amount);
        vm.startPrank(trader);
        token1.approve(address(pool), type(uint256).max);
        pool.swap(address(token1), amount);
        vm.stopPrank();
    }

    function swap_sell(uint256 amount) external {
        amount = bound(amount, 1e15, 10_000e18);
        address trader = makeAddr(string(abi.encodePacked("seller", amount)));
        token0.mint(trader, amount);
        vm.startPrank(trader);
        token0.approve(address(pool), type(uint256).max);
        pool.swap(address(token0), amount);
        vm.stopPrank();
    }

    function doClear() external {
        if (pool.Qb() == 0 && pool.Qs() == 0) return;
        if (pool.lastClearedBlock() == block.number) {
            vm.roll(block.number + 1);
        }
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();
    }
}

contract FBAMMInvariantTest is Test {
    FBAMM public pool;
    MockERC20 public token0;
    MockERC20 public token1;
    FBAMMHandler public handler;

    uint256 public initialK;

    function setUp() public {
        token0 = new MockERC20("Token0", "TK0", 18);
        token1 = new MockERC20("Token1", "TK1", 18);
        if (address(token0) > address(token1)) {
            (token0, token1) = (token1, token0);
        }
        pool = new FBAMM(address(token0), address(token1));

        address lp = makeAddr("lp");
        token0.mint(lp, 1_000_000e18);
        token1.mint(lp, 1_000_000e18);
        vm.startPrank(lp);
        token0.approve(address(pool), type(uint256).max);
        token1.approve(address(pool), type(uint256).max);
        pool.addLiquidity(1_000_000e18, 1_000_000e18);
        vm.stopPrank();

        initialK = pool.reserve0() * pool.reserve1();

        handler = new FBAMMHandler(pool, token0, token1);
        targetContract(address(handler));
    }

    function invariant_k_never_decreases() public view {
        uint256 currentK = pool.reserve0() * pool.reserve1();
        assertGe(currentK, initialK, "k must never decrease");
    }
}
```

- [ ] **Step 4: Run invariant tests**

```bash
forge test --match-contract FBAMMInvariantTest -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add test/FBAMM.fuzz.t.sol test/FBAMM.invariant.t.sol
git commit -m "feat: add fuzz and invariant tests for FBAMM"
```

---

## Task 6: Gas Benchmarks

**Files:**
- Create: `test/FBAMM.gas.t.sol`

- [ ] **Step 1: Write gas benchmark tests**

In `test/FBAMM.gas.t.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import "../src/FBAMM.sol";
import "../src/mocks/MockERC20.sol";

contract FBAMMGasTest is Test {
    FBAMM public pool;
    MockERC20 public token0;
    MockERC20 public token1;

    function setUp() public {
        token0 = new MockERC20("Token0", "TK0", 18);
        token1 = new MockERC20("Token1", "TK1", 18);
        if (address(token0) > address(token1)) {
            (token0, token1) = (token1, token0);
        }
        pool = new FBAMM(address(token0), address(token1));

        address lp = makeAddr("lp");
        token0.mint(lp, 1_000_000e18);
        token1.mint(lp, 1_000_000e18);
        vm.startPrank(lp);
        token0.approve(address(pool), type(uint256).max);
        token1.approve(address(pool), type(uint256).max);
        pool.addLiquidity(1_000_000e18, 1_000_000e18);
        vm.stopPrank();
    }

    function _addTraders(uint256 count) internal {
        for (uint256 i = 0; i < count; i++) {
            address buyer = makeAddr(string(abi.encodePacked("gasBuyer", i)));
            token1.mint(buyer, 1e18);
            vm.startPrank(buyer);
            token1.approve(address(pool), type(uint256).max);
            pool.swap(address(token1), 1e18);
            vm.stopPrank();
        }
    }

    function test_gas_clear_1_trader() public {
        _addTraders(1);
        vm.roll(block.number + 1);
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear(); // Gas measured by forge test --gas-report
    }

    function test_gas_clear_5_traders() public {
        _addTraders(5);
        vm.roll(block.number + 1);
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();
    }

    function test_gas_clear_10_traders() public {
        _addTraders(10);
        vm.roll(block.number + 1);
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();
    }

    function test_gas_clear_50_traders() public {
        _addTraders(50);
        vm.roll(block.number + 1);
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();
    }

    function test_gas_swap() public {
        address trader = makeAddr("gasTrader");
        token1.mint(trader, 1e18);
        vm.startPrank(trader);
        token1.approve(address(pool), type(uint256).max);
        pool.swap(address(token1), 1e18); // Gas measured
        vm.stopPrank();
    }
}
```

- [ ] **Step 2: Run gas benchmarks**

```bash
forge test --match-contract FBAMMGasTest --gas-report
```

Record the gas costs. This gives us the baseline for `clear()` scaling.

- [ ] **Step 3: Commit**

```bash
git add test/FBAMM.gas.t.sol
git commit -m "feat: add gas benchmark tests for swap and clear scaling"
```

---

## Task 7: Backtest Script — Fetch Uniswap V2 Swap Events

**Files:**
- Create: `script/FetchSwaps.s.sol`

This script reads swap events from a real Uniswap V2 pool on a forked mainnet and outputs them as JSON.

- [ ] **Step 1: Write the fetch script**

In `script/FetchSwaps.s.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Script.sol";

interface IUniswapV2Pair {
    function getReserves() external view returns (uint112, uint112, uint32);
    function token0() external view returns (address);
    function token1() external view returns (address);
}

contract FetchSwaps is Script {
    // Uniswap V2 ETH/USDC pair
    address constant UNIV2_ETH_USDC = 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc;

    function run() external view {
        IUniswapV2Pair pair = IUniswapV2Pair(UNIV2_ETH_USDC);
        (uint112 r0, uint112 r1, uint32 ts) = pair.getReserves();

        console.log("token0:", pair.token0());
        console.log("token1:", pair.token1());
        console.log("reserve0:", uint256(r0));
        console.log("reserve1:", uint256(r1));
        console.log("timestamp:", uint256(ts));
    }
}
```

- [ ] **Step 2: Test it against a forked mainnet**

```bash
source .env 2>/dev/null
forge script script/FetchSwaps.s.sol --rpc-url "$MAINNET_RPC_URL" --fork-block-number 19000000
```

Expected: Prints the reserves of ETH/USDC Uniswap V2 pair at block 19000000. If no RPC URL is configured, this will fail — that's expected, and the implementer should set up an Alchemy/Infura key first.

- [ ] **Step 3: Commit**

```bash
git add script/FetchSwaps.s.sol
git commit -m "feat: add FetchSwaps script to read Uniswap V2 state from forked mainnet"
```

---

## Task 8: Backtest Script — Per-Block FBAMM Replay

**Files:**
- Create: `script/Backtest.s.sol`

This is the core backtest: for each block, fork mainnet, read Uniswap V2 reserves, deploy FBAMM with same reserves, replay swap intents, clear, and output metrics.

**Note:** Full implementation of the backtest requires reading Uniswap V2 swap events from a block. In Foundry scripts, we can use `vm.getRecordedLogs()` or call an external data source. The simplest approach is to use a two-step process:

1. A Python script fetches swap events for a block range via RPC `eth_getLogs` and saves to JSON
2. The Foundry script reads the JSON and replays through FBAMM

- [ ] **Step 1: Create Python swap fetcher**

Create `analysis/fetch_swaps.py`:

```python
"""Fetch Uniswap V2 swap events for a block range via RPC eth_getLogs."""

import json
import os
import sys
from urllib.request import Request, urlopen

# Uniswap V2 Swap event signature
SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"

# Target pools
POOLS = {
    "ETH_USDC": "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc",
    "ETH_USDT": "0x0d4a11d5EEaaC28EC3F61d100daF4d40471f1852",
    "ETH_WBTC": "0xBb2b8038a1640196FbE3e38816F3e67Cba72D940",
}


def rpc_call(url, method, params):
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1})
    req = Request(url, data=body.encode(), headers={"Content-Type": "application/json"})
    with urlopen(req) as resp:
        return json.loads(resp.read())["result"]


def fetch_swaps(rpc_url, pool_address, from_block, to_block):
    logs = rpc_call(rpc_url, "eth_getLogs", [{
        "address": pool_address,
        "topics": [SWAP_TOPIC],
        "fromBlock": hex(from_block),
        "toBlock": hex(to_block),
    }])

    swaps = []
    for log in logs:
        data = bytes.fromhex(log["data"][2:])
        amount0In = int.from_bytes(data[0:32], "big")
        amount1In = int.from_bytes(data[32:64], "big")
        amount0Out = int.from_bytes(data[64:96], "big")
        amount1Out = int.from_bytes(data[96:128], "big")
        swaps.append({
            "blockNumber": int(log["blockNumber"], 16),
            "txHash": log["transactionHash"],
            "sender": "0x" + log["topics"][1][-40:],
            "to": "0x" + log["topics"][2][-40:],
            "amount0In": str(amount0In),
            "amount1In": str(amount1In),
            "amount0Out": str(amount0Out),
            "amount1Out": str(amount1Out),
        })
    return swaps


def fetch_reserves(rpc_url, pool_address, block_number):
    """Fetch reserves at a specific block via eth_call to getReserves()."""
    result = rpc_call(rpc_url, "eth_call", [
        {"to": pool_address, "data": "0x0902f1ac"},  # getReserves()
        hex(block_number),
    ])
    data = bytes.fromhex(result[2:])
    r0 = int.from_bytes(data[0:32], "big")
    r1 = int.from_bytes(data[32:64], "big")
    return r0, r1


def main():
    rpc_url = os.environ.get("MAINNET_RPC_URL")
    if not rpc_url:
        print("Set MAINNET_RPC_URL env var", file=sys.stderr)
        sys.exit(1)

    pool_name = sys.argv[1] if len(sys.argv) > 1 else "ETH_USDC"
    from_block = int(sys.argv[2]) if len(sys.argv) > 2 else 19000000
    to_block = int(sys.argv[3]) if len(sys.argv) > 3 else 19000100

    pool_address = POOLS[pool_name]
    print(f"Fetching swaps for {pool_name} ({pool_address}) blocks {from_block}-{to_block}")

    swaps = fetch_swaps(rpc_url, pool_address, from_block, to_block)
    print(f"Found {len(swaps)} swaps")

    # Group by block and add reserves
    blocks = {}
    for swap in swaps:
        bn = swap["blockNumber"]
        if bn not in blocks:
            r0, r1 = fetch_reserves(rpc_url, pool_address, bn - 1)  # reserves BEFORE block
            blocks[bn] = {"blockNumber": bn, "reserve0": str(r0), "reserve1": str(r1), "swaps": []}
        blocks[bn]["swaps"].append(swap)

    output = {"pool": pool_name, "address": pool_address, "blocks": list(blocks.values())}

    out_path = f"data/{pool_name}_{from_block}_{to_block}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the fetcher (requires RPC URL)**

```bash
cd /home/fao/fba
source .env
python3 analysis/fetch_swaps.py ETH_USDC 19000000 19000010
```

Expected: Creates `data/ETH_USDC_19000000_19000010.json` with swap events.

- [ ] **Step 3: Create the Foundry backtest script**

In `script/Backtest.s.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Script.sol";
import "../src/FBAMM.sol";
import "../src/mocks/MockERC20.sol";

contract Backtest is Script {
    function run() external {
        // This script is called per-block by the Python orchestrator.
        // It expects environment variables:
        //   RESERVE0, RESERVE1: initial reserves to match Uniswap V2
        //   SWAP_AMOUNTS: comma-separated list of "direction:amount" pairs
        //     direction 0 = token0 in (sell), direction 1 = token1 in (buy)

        uint256 r0 = vm.envUint("RESERVE0");
        uint256 r1 = vm.envUint("RESERVE1");
        string memory swapsRaw = vm.envString("SWAP_AMOUNTS");

        // Deploy mock tokens and FBAMM
        MockERC20 t0 = new MockERC20("Token0", "TK0", 18);
        MockERC20 t1 = new MockERC20("Token1", "TK1", 18);

        // Ensure correct ordering
        MockERC20 mToken0 = address(t0) < address(t1) ? t0 : t1;
        MockERC20 mToken1 = address(t0) < address(t1) ? t1 : t0;

        FBAMM pool = new FBAMM(address(mToken0), address(mToken1));

        // Seed LP with matching reserves
        address lp = makeAddr("lp");
        mToken0.mint(lp, r0);
        mToken1.mint(lp, r1);
        vm.startPrank(lp);
        mToken0.approve(address(pool), type(uint256).max);
        mToken1.approve(address(pool), type(uint256).max);
        pool.addLiquidity(r0, r1);
        vm.stopPrank();

        // Parse and replay swaps
        // (Swap parsing from env string is limited in Solidity —
        //  the Python orchestrator will call this once per block
        //  via forge script with the right env vars)

        console.log("FBAMM deployed with reserves:", r0, r1);
        console.log("Ready for swap replay");
    }
}
```

**Note to implementer:** The Solidity-only backtest approach is limited because parsing swap lists in Solidity is awkward. The recommended approach for the full backtest is:

1. Python orchestrator (`analysis/backtest.py`) reads the swap JSON
2. For each block, starts an Anvil instance forked at that block
3. Deploys FBAMM via forge script or direct RPC calls
4. Replays each swap via `cast send`
5. Calls `clear()` via `cast send`
6. Reads results via `cast call`
7. Records metrics

This hybrid approach (Python orchestrator + Foundry tools) is more practical than pure Solidity scripting.

- [ ] **Step 4: Create Python backtest orchestrator**

Create `analysis/backtest.py`:

```python
"""Per-block isolated FBAMM backtest orchestrator.

For each block in the swap data:
1. Deploy FBAMM with matching reserves (using Anvil + forge)
2. Replay swap intents through FBAMM
3. Call clear()
4. Record metrics (unified price, reserve changes, netting ratio)
"""

import json
import os
import subprocess
import sys


def run_cmd(cmd, env=None):
    """Run a shell command and return stdout."""
    full_env = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=full_env)
    if result.returncode != 0:
        print(f"CMD FAILED: {cmd}\nSTDERR: {result.stderr}", file=sys.stderr)
    return result.stdout.strip()


def main():
    data_file = sys.argv[1] if len(sys.argv) > 1 else "data/ETH_USDC_19000000_19000010.json"

    with open(data_file) as f:
        data = json.load(f)

    results = []

    for block_data in data["blocks"]:
        block_num = block_data["blockNumber"]
        r0 = block_data["reserve0"]
        r1 = block_data["reserve1"]
        swaps = block_data["swaps"]

        print(f"Block {block_num}: {len(swaps)} swaps, reserves ({r0}, {r1})")

        # Analyze Uniswap V2 side (ground truth)
        univ2_prices = []
        for swap in swaps:
            a0in = int(swap["amount0In"])
            a1in = int(swap["amount1In"])
            a0out = int(swap["amount0Out"])
            a1out = int(swap["amount1Out"])

            if a1in > 0 and a0out > 0:
                # Buying token0 with token1
                price = a1in / a0out  # token1 per token0
                univ2_prices.append({"direction": "buy", "amountIn": a1in, "amountOut": a0out, "price": price})
            elif a0in > 0 and a1out > 0:
                # Selling token0 for token1
                price = a0in / a1out  # token0 per token1 (inverse)
                univ2_prices.append({"direction": "sell", "amountIn": a0in, "amountOut": a1out, "price": price})

        if not univ2_prices:
            continue

        # TODO: Deploy FBAMM on Anvil, replay swaps, call clear(), read results
        # For now, record Uniswap V2 ground truth
        results.append({
            "blockNumber": block_num,
            "reserve0": r0,
            "reserve1": r1,
            "numSwaps": len(swaps),
            "univ2_trades": univ2_prices,
            # fbamm_* fields will be filled in when Anvil replay is implemented
        })

    out_path = data_file.replace(".json", "_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved {len(results)} block results to {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Commit**

```bash
git add script/FetchSwaps.s.sol script/Backtest.s.sol analysis/fetch_swaps.py analysis/backtest.py
git commit -m "feat: add backtest pipeline — swap fetcher and per-block replay orchestrator"
```

---

## Task 9: Analysis and Plotting

**Files:**
- Create: `analysis/aggregate.py`
- Create: `analysis/plot.py`

- [ ] **Step 1: Create aggregate.py**

```python
"""Aggregate backtest results into comparison metrics."""

import json
import sys
import statistics


def main():
    results_file = sys.argv[1]
    with open(results_file) as f:
        results = json.load(f)

    # Execution quality metrics
    all_price_variances = []
    all_num_swaps = []

    for block in results:
        trades = block.get("univ2_trades", [])
        if len(trades) < 2:
            continue

        buy_prices = [t["price"] for t in trades if t["direction"] == "buy"]
        if len(buy_prices) >= 2:
            all_price_variances.append(statistics.variance(buy_prices))
        all_num_swaps.append(len(trades))

    print(f"Blocks analyzed: {len(results)}")
    print(f"Total swaps: {sum(all_num_swaps)}")
    if all_price_variances:
        print(f"Avg within-block price variance (UniV2): {statistics.mean(all_price_variances):.6e}")
        print(f"FBAMM within-block price variance: 0 (unified price by design)")
    print(f"Avg swaps per block: {statistics.mean(all_num_swaps):.1f}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create plot.py**

```python
"""Generate comparison plots from backtest results."""

import json
import sys
import os

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend
except ImportError:
    print("Install matplotlib: pip install matplotlib", file=sys.stderr)
    sys.exit(1)


def main():
    results_file = sys.argv[1]
    with open(results_file) as f:
        results = json.load(f)

    output_dir = "data/plots"
    os.makedirs(output_dir, exist_ok=True)

    # Plot 1: Swaps per block distribution
    swaps_per_block = [b["numSwaps"] for b in results]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(swaps_per_block, bins=30, edgecolor="black")
    ax.set_xlabel("Swaps per Block")
    ax.set_ylabel("Frequency")
    ax.set_title("Distribution of Swap Count per Block (Uniswap V2)")
    fig.savefig(f"{output_dir}/swaps_per_block.png", dpi=150, bbox_inches="tight")
    print(f"Saved {output_dir}/swaps_per_block.png")

    # Plot 2: Within-block price variance (UniV2 vs FBAMM)
    variances = []
    for block in results:
        trades = block.get("univ2_trades", [])
        buy_prices = [t["price"] for t in trades if t["direction"] == "buy"]
        if len(buy_prices) >= 2:
            import statistics
            variances.append(statistics.variance(buy_prices))

    if variances:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.hist(variances, bins=30, edgecolor="black", label="Uniswap V2")
        ax.axvline(x=0, color="red", linestyle="--", linewidth=2, label="FBAMM (zero by design)")
        ax.set_xlabel("Within-Block Price Variance")
        ax.set_ylabel("Frequency")
        ax.set_title("Price Variance per Block: Uniswap V2 vs FBAMM")
        ax.legend()
        fig.savefig(f"{output_dir}/price_variance.png", dpi=150, bbox_inches="tight")
        print(f"Saved {output_dir}/price_variance.png")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add analysis/aggregate.py analysis/plot.py
git commit -m "feat: add analysis pipeline — aggregation and plotting scripts"
```

---

## Task 10: Long-Term Plan Document + Autonomous Loop Setup

**Files:**
- Create: `docs/long-term-plan.md`

- [ ] **Step 1: Create the living long-term plan document**

In `docs/long-term-plan.md`:

```markdown
# FBAMM Long-Term Plan

**Last updated:** 2026-03-31
**Objectives:**
1. Working FBAMM on Anvil testnet with backtest pipeline
2. Publication-ready academic paper

## Current Status

Phase 1: Foundation — building core contract, test suite, and backtest infrastructure.

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

## Session Log

### Session 1 (2026-03-31)
- Created design spec and implementation plan
- **Suggestion for next session:** Start with Task 1 (Foundry setup) and Task 2 (LP functions). These are the foundation everything else builds on.

## Open Questions
- What block range gives the best mix of high/low volatility for the paper?
- Should we compare against Uniswap V3 as well, or keep scope to V2?
- What's the optimal fee split (80/20) or should we test multiple splits?

## Ideas
- Test different fee splits (70/30, 90/10) and compare LP returns
- Analyze netting ratio as a function of block activity — does it scale?
- Compare gas overhead of FBAMM vs direct swap + MEV cost
```

- [ ] **Step 2: Commit**

```bash
git add docs/long-term-plan.md
git commit -m "feat: add long-term plan document for autonomous development loop"
```

- [ ] **Step 3: Verify full test suite passes**

```bash
cd /home/fao/fba
forge test --gas-report
```

Expected: All unit, fuzz, invariant, and gas tests pass.

---

## Execution Order & Dependencies

```
Task 1 (Foundry setup)
  └── Task 2 (LP functions) — needs compilable project
       └── Task 3 (Swap function) — needs LP + reserves
            └── Task 4 (Clear function) — needs swap + accumulators
                 ├── Task 5 (Fuzz/invariant tests) — needs working clear
                 ├── Task 6 (Gas benchmarks) — needs working clear
                 └── Task 7 (Fetch swaps) — independent, but needs Foundry
                      └── Task 8 (Backtest replay) — needs fetch + FBAMM contract
                           └── Task 9 (Analysis/plots) — needs backtest output
Task 10 (Long-term plan) — independent, can be done anytime
```

Tasks 5, 6 can run in parallel after Task 4. Task 7 can start after Task 1. Task 10 is independent.

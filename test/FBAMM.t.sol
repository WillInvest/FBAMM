// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import {FBAMM} from "../src/FBAMM.sol";
import {MockERC20} from "../src/mocks/MockERC20.sol";

contract FBAMMTest is Test {
    FBAMM pool;
    MockERC20 token0;
    MockERC20 token1;

    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address dead = address(0xdead);

    uint256 constant MINIMUM_LIQUIDITY = 1000;

    function setUp() public {
        // Deploy two tokens and ensure token0 < token1 by address
        MockERC20 tokenA = new MockERC20("Token A", "TKA", 18);
        MockERC20 tokenB = new MockERC20("Token B", "TKB", 18);

        if (address(tokenA) < address(tokenB)) {
            token0 = tokenA;
            token1 = tokenB;
        } else {
            token0 = tokenB;
            token1 = tokenA;
        }

        pool = new FBAMM(address(token0), address(token1));

        // Fund alice and bob
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
        uint256 amount0 = 100e18;
        uint256 amount1 = 100e18;

        vm.startPrank(alice);
        uint256 lpTokens = pool.addLiquidity(amount0, amount1);
        vm.stopPrank();

        // sqrt(100e18 * 100e18) = 100e18, minus MINIMUM_LIQUIDITY
        uint256 expectedLp = 100e18 - MINIMUM_LIQUIDITY;
        assertEq(lpTokens, expectedLp, "LP tokens minted incorrect");

        // MINIMUM_LIQUIDITY locked to dead address
        assertEq(pool.balanceOf(dead), MINIMUM_LIQUIDITY, "MINIMUM_LIQUIDITY not locked");

        // Alice holds the LP tokens
        assertEq(pool.balanceOf(alice), expectedLp, "Alice LP balance incorrect");

        // Reserves updated
        assertEq(pool.reserve0(), amount0, "reserve0 incorrect");
        assertEq(pool.reserve1(), amount1, "reserve1 incorrect");

        // Tokens transferred from alice
        assertEq(token0.balanceOf(alice), 1000e18 - amount0, "alice token0 balance");
        assertEq(token1.balanceOf(alice), 1000e18 - amount1, "alice token1 balance");
    }

    function test_addLiquidity_secondDeposit_proportional() public {
        // First deposit by alice
        vm.startPrank(alice);
        pool.addLiquidity(100e18, 100e18);
        vm.stopPrank();

        uint256 totalSupplyBefore = pool.totalSupply();

        // Second deposit by bob — proportional (50e18 each for 1:1 pool)
        vm.startPrank(bob);
        uint256 lpTokens = pool.addLiquidity(50e18, 50e18);
        vm.stopPrank();

        // Proportional: min(50e18 * totalSupply / 100e18, 50e18 * totalSupply / 100e18)
        uint256 expectedLp = (50e18 * totalSupplyBefore) / 100e18;
        assertEq(lpTokens, expectedLp, "Proportional LP tokens incorrect");

        // Reserves updated
        assertEq(pool.reserve0(), 150e18, "reserve0 after second deposit");
        assertEq(pool.reserve1(), 150e18, "reserve1 after second deposit");

        // Bob holds his LP tokens
        assertEq(pool.balanceOf(bob), expectedLp, "Bob LP balance incorrect");
    }

    function test_removeLiquidity() public {
        // Alice adds liquidity
        vm.startPrank(alice);
        uint256 lpTokens = pool.addLiquidity(100e18, 100e18);

        // Alice removes all her LP tokens
        (uint256 out0, uint256 out1) = pool.removeLiquidity(lpTokens);
        vm.stopPrank();

        // Because MINIMUM_LIQUIDITY is locked, alice can't get 100% back
        // out0 = lpTokens * reserve0 / totalSupply = (100e18 - 1000) * 100e18 / 100e18
        // = 100e18 - 1000
        uint256 expectedOut = 100e18 - MINIMUM_LIQUIDITY;
        assertEq(out0, expectedOut, "removed amount0 incorrect");
        assertEq(out1, expectedOut, "removed amount1 incorrect");

        // Alice LP balance is 0
        assertEq(pool.balanceOf(alice), 0, "Alice should have 0 LP");

        // Reserves should reflect the locked minimum liquidity share
        assertEq(pool.reserve0(), MINIMUM_LIQUIDITY, "reserve0 should be MINIMUM_LIQUIDITY");
        assertEq(pool.reserve1(), MINIMUM_LIQUIDITY, "reserve1 should be MINIMUM_LIQUIDITY");

        // Alice gets her tokens back (minus dust locked)
        assertEq(token0.balanceOf(alice), 1000e18 - MINIMUM_LIQUIDITY, "alice token0 after remove");
        assertEq(token1.balanceOf(alice), 1000e18 - MINIMUM_LIQUIDITY, "alice token1 after remove");
    }

    // ── Swap tests ──────────────────────────────────────────────────

    function test_swap_buyToken0() public {
        vm.prank(alice);
        pool.addLiquidity(100e18, 100e18);

        uint256 swapAmount = 10e18;
        uint256 fee = (swapAmount * 30) / 10000;
        uint256 netAmount = swapAmount - fee;

        vm.prank(bob);
        pool.swap(address(token1), swapAmount);

        assertEq(pool.Qb(), netAmount, "Qb should increase by net amount");
        assertEq(pool.Qs(), 0, "Qs should be unchanged");
        assertEq(pool.batchBuyOrders(bob), netAmount);
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
        pool.swap(address(token1), amount1);

        vm.prank(bob);
        pool.swap(address(token1), amount2);

        assertEq(pool.Qb(), (amount1 - fee1) + (amount2 - fee2));
    }
}

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
        amount = bound(amount, 1e15, 100_000e18);

        address trader = makeAddr("trader");
        token1.mint(trader, amount);
        vm.startPrank(trader);
        token1.approve(address(pool), type(uint256).max);
        pool.swap(address(token1), amount);
        vm.stopPrank();

        vm.roll(block.number + 1);

        uint256 kBefore = pool.reserve0() * pool.reserve1();

        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();

        uint256 kAfter = pool.reserve0() * pool.reserve1();
        assertGe(kAfter, kBefore, "k should not decrease");
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
        assertGt(token0.balanceOf(buyer), 0, "Buyer should get token0");
        assertGt(token1.balanceOf(seller), 0, "Seller should get token1");
    }
}

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

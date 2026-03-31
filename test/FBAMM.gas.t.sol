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

    function _addBuyers(uint256 count) internal {
        for (uint256 i = 0; i < count; i++) {
            address buyer = makeAddr(string(abi.encodePacked("gasBuyer", i)));
            token1.mint(buyer, 1e18);
            vm.startPrank(buyer);
            token1.approve(address(pool), type(uint256).max);
            pool.swap(address(token1), 1e18);
            vm.stopPrank();
        }
    }

    function _addMixedTraders(uint256 buyCount, uint256 sellCount) internal {
        for (uint256 i = 0; i < buyCount; i++) {
            address buyer = makeAddr(string(abi.encodePacked("gasBuyer", i)));
            token1.mint(buyer, 1e18);
            vm.startPrank(buyer);
            token1.approve(address(pool), type(uint256).max);
            pool.swap(address(token1), 1e18);
            vm.stopPrank();
        }
        for (uint256 i = 0; i < sellCount; i++) {
            address seller = makeAddr(string(abi.encodePacked("gasSeller", i)));
            token0.mint(seller, 1e18);
            vm.startPrank(seller);
            token0.approve(address(pool), type(uint256).max);
            pool.swap(address(token0), 1e18);
            vm.stopPrank();
        }
    }

    function test_gas_clear_1_trader() public {
        _addBuyers(1);
        vm.roll(block.number + 1);
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();
    }

    function test_gas_clear_5_traders() public {
        _addBuyers(5);
        vm.roll(block.number + 1);
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();
    }

    function test_gas_clear_10_traders() public {
        _addBuyers(10);
        vm.roll(block.number + 1);
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();
    }

    function test_gas_clear_50_traders() public {
        _addBuyers(50);
        vm.roll(block.number + 1);
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();
    }

    function test_gas_clear_10_mixed() public {
        _addMixedTraders(5, 5);
        vm.roll(block.number + 1);
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();
    }

    function test_gas_clear_50_mixed() public {
        _addMixedTraders(25, 25);
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
        pool.swap(address(token1), 1e18);
        vm.stopPrank();
    }
}

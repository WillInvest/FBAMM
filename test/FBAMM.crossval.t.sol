// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import {FBAMM} from "../src/FBAMM.sol";
import {MockERC20} from "../src/mocks/MockERC20.sol";

/// @notice Cross-validation test: runs same scenarios as analysis/test_backtest.py
/// Compare logged values to verify Python simulation matches Solidity contract.
contract FBAMMCrossValTest is Test {
    MockERC20 token0;
    MockERC20 token1;

    function _freshPool(uint256 r0, uint256 r1) internal returns (FBAMM pool) {
        token0 = new MockERC20("Token0", "TK0", 18);
        token1 = new MockERC20("Token1", "TK1", 18);
        if (address(token0) > address(token1)) {
            (token0, token1) = (token1, token0);
        }
        pool = new FBAMM(address(token0), address(token1));

        address lp = makeAddr("lp");
        token0.mint(lp, r0);
        token1.mint(lp, r1);
        vm.startPrank(lp);
        token0.approve(address(pool), type(uint256).max);
        token1.approve(address(pool), type(uint256).max);
        pool.addLiquidity(r0, r1);
        vm.stopPrank();
    }

    function _setupTrader(address pool_, string memory name, uint256 amount0, uint256 amount1) internal returns (address) {
        address trader = makeAddr(name);
        if (amount0 > 0) token0.mint(trader, amount0);
        if (amount1 > 0) token1.mint(trader, amount1);
        vm.startPrank(trader);
        token0.approve(pool_, type(uint256).max);
        token1.approve(pool_, type(uint256).max);
        vm.stopPrank();
        return trader;
    }

    function test_crossval_singleBuyer() public {
        FBAMM pool = _freshPool(1000e18, 1000e18);

        uint256 buyAmount = 10e18;
        address buyer = _setupTrader(address(pool), "buyer", 0, buyAmount);

        vm.prank(buyer);
        pool.swap(address(token1), buyAmount);

        vm.roll(block.number + 1);
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();

        uint256 output = token0.balanceOf(buyer);
        emit log_named_uint("CROSSVAL single_buyer token0_output", output);
        emit log_named_uint("CROSSVAL single_buyer reserve0_after", pool.reserve0());
        emit log_named_uint("CROSSVAL single_buyer reserve1_after", pool.reserve1());

        // Verify against hand-calculated value
        uint256 fee = (buyAmount * 30) / 10000;
        uint256 net = buyAmount - fee;
        uint256 expected = (net * 1000e18) / (1000e18 + net);
        assertEq(output, expected, "Single buyer output should match formula");
    }

    function test_crossval_balanced() public {
        FBAMM pool = _freshPool(1000e18, 1000e18);

        uint256 amount = 10e18;
        address buyer = _setupTrader(address(pool), "buyer", 0, amount);
        address seller = _setupTrader(address(pool), "seller", amount, 0);

        vm.prank(buyer);
        pool.swap(address(token1), amount);
        vm.prank(seller);
        pool.swap(address(token0), amount);

        vm.roll(block.number + 1);
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();

        uint256 buyerOut = token0.balanceOf(buyer);
        uint256 sellerOut = token1.balanceOf(seller);

        emit log_named_uint("CROSSVAL balanced buyer_token0_output", buyerOut);
        emit log_named_uint("CROSSVAL balanced seller_token1_output", sellerOut);
        emit log_named_uint("CROSSVAL balanced reserve0_after", pool.reserve0());
        emit log_named_uint("CROSSVAL balanced reserve1_after", pool.reserve1());

        uint256 fee = (amount * 30) / 10000;
        uint256 net = amount - fee;
        // Balanced: buyer gets net token0 (from seller), seller gets net token1 (from buyer)
        assertEq(buyerOut, net, "Balanced buyer should get full netted amount");
        assertEq(sellerOut, net, "Balanced seller should get full netted amount");
    }

    function test_crossval_unbalanced() public {
        FBAMM pool = _freshPool(1000e18, 1000e18);

        uint256 buyAmount = 20e18;
        uint256 sellAmount = 10e18;
        address buyer = _setupTrader(address(pool), "buyer", 0, buyAmount);
        address seller = _setupTrader(address(pool), "seller", sellAmount, 0);

        vm.prank(buyer);
        pool.swap(address(token1), buyAmount);
        vm.prank(seller);
        pool.swap(address(token0), sellAmount);

        vm.roll(block.number + 1);
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();

        uint256 buyerOut = token0.balanceOf(buyer);
        uint256 sellerOut = token1.balanceOf(seller);

        emit log_named_uint("CROSSVAL unbalanced buyer_token0_output", buyerOut);
        emit log_named_uint("CROSSVAL unbalanced seller_token1_output", sellerOut);
        emit log_named_uint("CROSSVAL unbalanced reserve0_after", pool.reserve0());
        emit log_named_uint("CROSSVAL unbalanced reserve1_after", pool.reserve1());

        uint256 buyFee = (buyAmount * 30) / 10000;
        uint256 sellFee = (sellAmount * 30) / 10000;
        uint256 netBuy = buyAmount - buyFee;
        uint256 netSell = sellAmount - sellFee;
        uint256 netDemand = netBuy - netSell;
        uint256 ammOut = (netDemand * 1000e18) / (1000e18 + netDemand);

        uint256 expectedBuyerOut = netSell + ammOut; // from sellers + AMM
        uint256 expectedSellerOut = netSell; // matched portion from buyers

        assertEq(buyerOut, expectedBuyerOut, "Unbalanced buyer output");
        assertEq(sellerOut, expectedSellerOut, "Unbalanced seller output");
    }
}

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import {FBAMM} from "../src/FBAMM.sol";
import {MockERC20} from "../src/mocks/MockERC20.sol";

contract FBAMMIntegrationTest is Test {
    FBAMM pool;
    MockERC20 token0;
    MockERC20 token1;

    // We track which token is WETH and which is USDC after address sorting
    MockERC20 weth;
    MockERC20 usdc;

    // Realistic reserves: 1000 ETH, 2M USDC (~$2000/ETH)
    uint256 constant INIT_WETH = 1000e18;       // 1000 WETH (18 decimals)
    uint256 constant INIT_USDC = 2_000_000e6;   // 2M USDC (6 decimals)

    // After sorting, these hold the correct reserve amounts for token0/token1
    uint256 initReserve0;
    uint256 initReserve1;

    // true if token0 == weth, false if token0 == usdc
    bool token0IsWeth;

    function setUp() public {
        weth = new MockERC20("Wrapped ETH", "WETH", 18);
        usdc = new MockERC20("USD Coin", "USDC", 6);

        // Sort by address for the pool constructor
        if (address(weth) < address(usdc)) {
            token0 = weth;
            token1 = usdc;
            token0IsWeth = true;
            initReserve0 = INIT_WETH;
            initReserve1 = INIT_USDC;
        } else {
            token0 = usdc;
            token1 = weth;
            token0IsWeth = false;
            initReserve0 = INIT_USDC;
            initReserve1 = INIT_WETH;
        }

        pool = new FBAMM(address(token0), address(token1));

        address lp = makeAddr("lp");
        token0.mint(lp, initReserve0);
        token1.mint(lp, initReserve1);
        vm.startPrank(lp);
        token0.approve(address(pool), type(uint256).max);
        token1.approve(address(pool), type(uint256).max);
        pool.addLiquidity(initReserve0, initReserve1);
        vm.stopPrank();
    }

    // ── Helpers ──────────────────────────────────────────────────────────

    /// Create a trader with funds and approvals
    function _createTrader(string memory name, uint256 wethAmt, uint256 usdcAmt) internal returns (address) {
        address trader = makeAddr(name);
        if (wethAmt > 0) weth.mint(trader, wethAmt);
        if (usdcAmt > 0) usdc.mint(trader, usdcAmt);
        vm.startPrank(trader);
        token0.approve(address(pool), type(uint256).max);
        token1.approve(address(pool), type(uint256).max);
        vm.stopPrank();
        return trader;
    }

    /// Simulate Uniswap V2: sequential constant-product swaps with 0.3% fee.
    /// isBuyETH[i] == true means trader deposits USDC to buy WETH.
    /// Returns outputs denominated in the output token for each trade.
    function _simulateUniV2(
        uint256 rWeth,
        uint256 rUsdc,
        bool[] memory isBuyETH,
        uint256[] memory amounts
    ) internal pure returns (uint256[] memory outputs, uint256 newRWeth, uint256 newRUsdc) {
        outputs = new uint256[](amounts.length);
        newRWeth = rWeth;
        newRUsdc = rUsdc;

        for (uint256 i = 0; i < amounts.length; i++) {
            uint256 fee = (amounts[i] * 30) / 10000;
            uint256 net = amounts[i] - fee;

            if (isBuyETH[i]) {
                // USDC in, WETH out
                outputs[i] = (net * newRWeth) / (newRUsdc + net);
                newRUsdc += amounts[i]; // full amount (incl fee) goes to reserves
                newRWeth -= outputs[i];
            } else {
                // WETH in, USDC out
                outputs[i] = (net * newRUsdc) / (newRWeth + net);
                newRWeth += amounts[i];
                newRUsdc -= outputs[i];
            }
        }
    }

    // ── Test: Block 1 — mixed buy/sell activity ─────────────────────────

    // Storage for mixed trading test to avoid stack-too-deep
    uint256[5] private _uniMixedOutputs;
    address[5] private _mixedTraders;

    function test_integration_block1_mixedTrading() public {
        _mixedTrading_setup();
        _mixedTrading_verify();
        _mixedTrading_log();
    }

    function _mixedTrading_setup() internal {
        // 5 traders: 3 buying ETH with USDC, 2 selling ETH for USDC
        _mixedTraders[0] = _createTrader("buyer1", 0, 4000e6);
        _mixedTraders[1] = _createTrader("buyer2", 0, 2000e6);
        _mixedTraders[2] = _createTrader("buyer3", 0, 1000e6);
        _mixedTraders[3] = _createTrader("seller1", 2e18, 0);
        _mixedTraders[4] = _createTrader("seller2", 1e18, 0);

        // UniV2 simulation
        bool[] memory isBuyETH = new bool[](5);
        uint256[] memory amounts = new uint256[](5);
        isBuyETH[0] = true;  amounts[0] = 4000e6;
        isBuyETH[1] = true;  amounts[1] = 2000e6;
        isBuyETH[2] = true;  amounts[2] = 1000e6;
        isBuyETH[3] = false; amounts[3] = 2e18;
        isBuyETH[4] = false; amounts[4] = 1e18;

        (uint256[] memory uniOutputs,,) = _simulateUniV2(INIT_WETH, INIT_USDC, isBuyETH, amounts);
        for (uint256 i = 0; i < 5; i++) _uniMixedOutputs[i] = uniOutputs[i];

        // FBAMM execution
        vm.prank(_mixedTraders[0]);
        pool.swap(address(usdc), 4000e6);
        vm.prank(_mixedTraders[1]);
        pool.swap(address(usdc), 2000e6);
        vm.prank(_mixedTraders[2]);
        pool.swap(address(usdc), 1000e6);
        vm.prank(_mixedTraders[3]);
        pool.swap(address(weth), 2e18);
        vm.prank(_mixedTraders[4]);
        pool.swap(address(weth), 1e18);

        vm.roll(block.number + 1);
        vm.prank(makeAddr("clearer"));
        pool.clear();
    }

    function _mixedTrading_verify() internal view {
        uint256 b1Out = weth.balanceOf(_mixedTraders[0]);
        uint256 b2Out = weth.balanceOf(_mixedTraders[1]);
        uint256 b3Out = weth.balanceOf(_mixedTraders[2]);
        uint256 s1Out = usdc.balanceOf(_mixedTraders[3]);
        uint256 s2Out = usdc.balanceOf(_mixedTraders[4]);

        assertGt(b1Out, 0, "buyer1 should get WETH");
        assertGt(b2Out, 0, "buyer2 should get WETH");
        assertGt(b3Out, 0, "buyer3 should get WETH");
        assertGt(s1Out, 0, "seller1 should get USDC");
        assertGt(s2Out, 0, "seller2 should get USDC");

        // Verify unified price for buyers via cross-multiplication
        uint256 net1 = 4000e6 - (4000e6 * 30) / 10000;
        uint256 net2 = 2000e6 - (2000e6 * 30) / 10000;
        uint256 net3 = 1000e6 - (1000e6 * 30) / 10000;

        assertApproxEqAbs(b1Out * net2, b2Out * net1, 1e12, "Buyers 1&2 should get unified price");
        assertApproxEqAbs(b2Out * net3, b3Out * net2, 1e12, "Buyers 2&3 should get unified price");

        // Verify unified price for sellers
        uint256 sNet1 = 2e18 - (2e18 * 30) / 10000;
        uint256 sNet2 = 1e18 - (1e18 * 30) / 10000;
        assertApproxEqAbs(s1Out * sNet2, s2Out * sNet1, 1e18, "Sellers should get unified price");
    }

    function _mixedTrading_log() internal {
        uint256 b1Out = weth.balanceOf(_mixedTraders[0]);
        uint256 b2Out = weth.balanceOf(_mixedTraders[1]);
        uint256 b3Out = weth.balanceOf(_mixedTraders[2]);
        uint256 s1Out = usdc.balanceOf(_mixedTraders[3]);
        uint256 s2Out = usdc.balanceOf(_mixedTraders[4]);

        emit log("=== UniV2 vs FBAMM: Block 1 Mixed Trading ===");
        emit log("--- Buyers (USDC -> WETH) ---");
        emit log_named_uint("UniV2  buyer1 WETH out", _uniMixedOutputs[0]);
        emit log_named_uint("FBAMM  buyer1 WETH out", b1Out);
        emit log_named_uint("UniV2  buyer2 WETH out", _uniMixedOutputs[1]);
        emit log_named_uint("FBAMM  buyer2 WETH out", b2Out);
        emit log_named_uint("UniV2  buyer3 WETH out", _uniMixedOutputs[2]);
        emit log_named_uint("FBAMM  buyer3 WETH out", b3Out);
        emit log("--- Sellers (WETH -> USDC) ---");
        emit log_named_uint("UniV2  seller1 USDC out", _uniMixedOutputs[3]);
        emit log_named_uint("FBAMM  seller1 USDC out", s1Out);
        emit log_named_uint("UniV2  seller2 USDC out", _uniMixedOutputs[4]);
        emit log_named_uint("FBAMM  seller2 USDC out", s2Out);

        // Price variance analysis
        uint256 uniPrice1 = (4000e6 * 1e18) / _uniMixedOutputs[0];
        uint256 uniPrice3 = (1000e6 * 1e18) / _uniMixedOutputs[2];
        uint256 fbammPrice = (4000e6 * 1e18) / b1Out;

        emit log("--- Effective price (USDC per WETH, scaled 1e18) ---");
        emit log_named_uint("UniV2  buyer1 price", uniPrice1);
        emit log_named_uint("UniV2  buyer3 price", uniPrice3);
        emit log_named_uint("FBAMM  uniform price", fbammPrice);
        uint256 spread = uniPrice3 > uniPrice1 ? uniPrice3 - uniPrice1 : uniPrice1 - uniPrice3;
        emit log_named_uint("UniV2  price spread (buyer1 vs buyer3)", spread);
        emit log("FBAMM  price spread: 0 (unified batch price)");
    }

    // ── Test: fully balanced block — netting advantage ──────────────────

    function test_integration_fullyBalanced() public {
        // Roughly balanced: $2000 USDC buying ETH vs 1 ETH selling (~$2000 worth)
        address buyer = _createTrader("buyer", 0, 2000e6);
        address seller = _createTrader("seller", 1e18, 0);

        // UniV2: buyer goes first, moves price up, then seller sells at higher price
        bool[] memory isBuyETH = new bool[](2);
        uint256[] memory amounts = new uint256[](2);
        isBuyETH[0] = true;  amounts[0] = 2000e6;
        isBuyETH[1] = false; amounts[1] = 1e18;
        (uint256[] memory uniOutputs,,) = _simulateUniV2(INIT_WETH, INIT_USDC, isBuyETH, amounts);

        // FBAMM
        vm.prank(buyer);
        pool.swap(address(usdc), 2000e6);
        vm.prank(seller);
        pool.swap(address(weth), 1e18);

        vm.roll(block.number + 1);
        address clearer = makeAddr("clearer");
        vm.prank(clearer);
        pool.clear();

        uint256 fbammBuyerOut = weth.balanceOf(buyer);
        uint256 fbammSellerOut = usdc.balanceOf(seller);

        assertGt(fbammBuyerOut, 0, "buyer should get WETH");
        assertGt(fbammSellerOut, 0, "seller should get USDC");

        emit log("=== UniV2 vs FBAMM: Fully Balanced Block ===");
        emit log_named_uint("UniV2  buyer  WETH out", uniOutputs[0]);
        emit log_named_uint("FBAMM  buyer  WETH out", fbammBuyerOut);
        emit log_named_uint("UniV2  seller USDC out", uniOutputs[1]);
        emit log_named_uint("FBAMM  seller USDC out", fbammSellerOut);

        // With netting, the pool absorbs less net demand, so prices should be better
        // In a perfectly balanced case, FBAMM can match internally without touching AMM
        emit log("--- Netting Analysis ---");
        emit log("When buy and sell flows roughly cancel, FBAMM nets internally");
        emit log("The AMM curve only handles residual net demand");
    }

    // ── Test: three consecutive blocks ──────────────────────────────────

    // Storage vars to avoid stack-too-deep in multi-block test
    uint256 private _cumUniBuyerWeth;
    uint256 private _cumUniSellerUsdc;
    uint256 private _cumFbammBuyerWeth;
    uint256 private _cumFbammSellerUsdc;

    function _poolWethReserve() internal view returns (uint256) {
        return token0IsWeth ? pool.reserve0() : pool.reserve1();
    }

    function _poolUsdcReserve() internal view returns (uint256) {
        return token0IsWeth ? pool.reserve1() : pool.reserve0();
    }

    function test_integration_threeBlocks() public {
        // Block 1: heavy buying pressure (ETH demand)
        // Block 2: balanced
        // Block 3: heavy selling pressure

        _runBlock1();
        _runBlock2();
        _runBlock3();

        // ── Cumulative comparison ───────────────────────────────────
        emit log("=== Cumulative 3-Block Summary ===");
        emit log_named_uint("UniV2  total buyer WETH received", _cumUniBuyerWeth);
        emit log_named_uint("FBAMM  total buyer WETH received", _cumFbammBuyerWeth);
        emit log_named_uint("UniV2  total seller USDC received", _cumUniSellerUsdc);
        emit log_named_uint("FBAMM  total seller USDC received", _cumFbammSellerUsdc);
    }

    function _runBlock1() internal {
        address b1 = _createTrader("b1_buyer1", 0, 5000e6);
        address b1b2 = _createTrader("b1_buyer2", 0, 3000e6);
        address b1s1 = _createTrader("b1_seller1", 1e18, 0);

        bool[] memory isBuy = new bool[](3);
        uint256[] memory amts = new uint256[](3);
        isBuy[0] = true;  amts[0] = 5000e6;
        isBuy[1] = true;  amts[1] = 3000e6;
        isBuy[2] = false; amts[2] = 1e18;
        (uint256[] memory uniOut,,) = _simulateUniV2(INIT_WETH, INIT_USDC, isBuy, amts);

        _cumUniBuyerWeth += uniOut[0] + uniOut[1];
        _cumUniSellerUsdc += uniOut[2];

        vm.prank(b1);
        pool.swap(address(usdc), 5000e6);
        vm.prank(b1b2);
        pool.swap(address(usdc), 3000e6);
        vm.prank(b1s1);
        pool.swap(address(weth), 1e18);

        vm.roll(block.number + 1);
        vm.prank(makeAddr("clearer1"));
        pool.clear();

        _cumFbammBuyerWeth += weth.balanceOf(b1) + weth.balanceOf(b1b2);
        _cumFbammSellerUsdc += usdc.balanceOf(b1s1);

        emit log("=== Block 1: Heavy Buy Pressure ===");
        emit log_named_uint("UniV2  buyer1 WETH", uniOut[0]);
        emit log_named_uint("FBAMM  buyer1 WETH", weth.balanceOf(b1));
        emit log_named_uint("UniV2  buyer2 WETH", uniOut[1]);
        emit log_named_uint("FBAMM  buyer2 WETH", weth.balanceOf(b1b2));
        emit log_named_uint("UniV2  seller1 USDC", uniOut[2]);
        emit log_named_uint("FBAMM  seller1 USDC", usdc.balanceOf(b1s1));
    }

    function _runBlock2() internal {
        uint256 rW = _poolWethReserve();
        uint256 rU = _poolUsdcReserve();

        address b2b = _createTrader("b2_buyer", 0, 2000e6);
        address b2s = _createTrader("b2_seller", 1e18, 0);

        bool[] memory isBuy = new bool[](2);
        uint256[] memory amts = new uint256[](2);
        isBuy[0] = true;  amts[0] = 2000e6;
        isBuy[1] = false; amts[1] = 1e18;
        (uint256[] memory uniOut,,) = _simulateUniV2(rW, rU, isBuy, amts);

        _cumUniBuyerWeth += uniOut[0];
        _cumUniSellerUsdc += uniOut[1];

        vm.prank(b2b);
        pool.swap(address(usdc), 2000e6);
        vm.prank(b2s);
        pool.swap(address(weth), 1e18);

        vm.roll(block.number + 1);
        vm.prank(makeAddr("clearer2"));
        pool.clear();

        _cumFbammBuyerWeth += weth.balanceOf(b2b);
        _cumFbammSellerUsdc += usdc.balanceOf(b2s);

        emit log("=== Block 2: Balanced Trading ===");
        emit log_named_uint("UniV2  buyer WETH", uniOut[0]);
        emit log_named_uint("FBAMM  buyer WETH", weth.balanceOf(b2b));
        emit log_named_uint("UniV2  seller USDC", uniOut[1]);
        emit log_named_uint("FBAMM  seller USDC", usdc.balanceOf(b2s));
    }

    function _runBlock3() internal {
        uint256 rW = _poolWethReserve();
        uint256 rU = _poolUsdcReserve();

        address b3b = _createTrader("b3_buyer", 0, 1000e6);
        address b3s1 = _createTrader("b3_seller1", 3e18, 0);
        address b3s2 = _createTrader("b3_seller2", 2e18, 0);

        bool[] memory isBuy = new bool[](3);
        uint256[] memory amts = new uint256[](3);
        isBuy[0] = true;  amts[0] = 1000e6;
        isBuy[1] = false; amts[1] = 3e18;
        isBuy[2] = false; amts[2] = 2e18;
        (uint256[] memory uniOut,,) = _simulateUniV2(rW, rU, isBuy, amts);

        _cumUniBuyerWeth += uniOut[0];
        _cumUniSellerUsdc += uniOut[1] + uniOut[2];

        vm.prank(b3b);
        pool.swap(address(usdc), 1000e6);
        vm.prank(b3s1);
        pool.swap(address(weth), 3e18);
        vm.prank(b3s2);
        pool.swap(address(weth), 2e18);

        vm.roll(block.number + 1);
        vm.prank(makeAddr("clearer3"));
        pool.clear();

        _cumFbammBuyerWeth += weth.balanceOf(b3b);
        _cumFbammSellerUsdc += usdc.balanceOf(b3s1) + usdc.balanceOf(b3s2);

        emit log("=== Block 3: Heavy Sell Pressure ===");
        emit log_named_uint("UniV2  buyer WETH", uniOut[0]);
        emit log_named_uint("FBAMM  buyer WETH", weth.balanceOf(b3b));
        emit log_named_uint("UniV2  seller1 USDC", uniOut[1]);
        emit log_named_uint("FBAMM  seller1 USDC", usdc.balanceOf(b3s1));
        emit log_named_uint("UniV2  seller2 USDC", uniOut[2]);
        emit log_named_uint("FBAMM  seller2 USDC", usdc.balanceOf(b3s2));
    }

    // ── Test: netting efficiency measurement ────────────────────────────

    function test_integration_nettingEfficiency() public {
        // Scenario: large opposing flows that mostly cancel out
        // 10 ETH worth of buys ($20,000) vs 9 ETH of sells
        // ~90% should net, only ~10% residual hits AMM

        address buyer1 = _createTrader("netBuyer1", 0, 10_000e6);
        address buyer2 = _createTrader("netBuyer2", 0, 10_000e6);
        address seller1 = _createTrader("netSeller1", 5e18, 0);
        address seller2 = _createTrader("netSeller2", 4e18, 0);

        // Submit swaps
        vm.prank(buyer1);
        pool.swap(address(usdc), 10_000e6);
        vm.prank(buyer2);
        pool.swap(address(usdc), 10_000e6);
        vm.prank(seller1);
        pool.swap(address(weth), 5e18);
        vm.prank(seller2);
        pool.swap(address(weth), 4e18);

        // Check accumulators before clearing
        uint256 qb = pool.Qb();
        uint256 qs = pool.Qs();

        emit log("=== Netting Efficiency ===");
        emit log_named_uint("Qb (buy accumulator, USDC net of fee)", qb);
        emit log_named_uint("Qs (sell accumulator, WETH net of fee)", qs);

        // The sell side contributes WETH; the buy side contributes USDC
        // At ~$2000/ETH, 9 ETH ~ $18,000 of sells vs $20,000 of buys
        // The netting matches internally, only residual hits AMM

        uint256 reservesBefore0 = pool.reserve0();
        uint256 reservesBefore1 = pool.reserve1();

        vm.roll(block.number + 1);
        vm.prank(makeAddr("clearer"));
        pool.clear();

        uint256 reservesAfter0 = pool.reserve0();
        uint256 reservesAfter1 = pool.reserve1();

        // Measure how much reserves actually moved (less = more netting)
        uint256 r0Delta = reservesAfter0 > reservesBefore0
            ? reservesAfter0 - reservesBefore0
            : reservesBefore0 - reservesAfter0;
        uint256 r1Delta = reservesAfter1 > reservesBefore1
            ? reservesAfter1 - reservesBefore1
            : reservesBefore1 - reservesAfter1;

        emit log_named_uint("Reserve0 before", reservesBefore0);
        emit log_named_uint("Reserve0 after", reservesAfter0);
        emit log_named_uint("Reserve0 delta (abs)", r0Delta);
        emit log_named_uint("Reserve1 before", reservesBefore1);
        emit log_named_uint("Reserve1 after", reservesAfter1);
        emit log_named_uint("Reserve1 delta (abs)", r1Delta);

        // Verify all traders got output
        assertGt(weth.balanceOf(buyer1), 0, "netBuyer1 should get WETH");
        assertGt(weth.balanceOf(buyer2), 0, "netBuyer2 should get WETH");
        assertGt(usdc.balanceOf(seller1), 0, "netSeller1 should get USDC");
        assertGt(usdc.balanceOf(seller2), 0, "netSeller2 should get USDC");

        emit log_named_uint("buyer1 WETH received", weth.balanceOf(buyer1));
        emit log_named_uint("buyer2 WETH received", weth.balanceOf(buyer2));
        emit log_named_uint("seller1 USDC received", usdc.balanceOf(seller1));
        emit log_named_uint("seller2 USDC received", usdc.balanceOf(seller2));

        // Compare with UniV2 for context
        bool[] memory isBuy = new bool[](4);
        uint256[] memory amts = new uint256[](4);
        isBuy[0] = true;  amts[0] = 10_000e6;
        isBuy[1] = true;  amts[1] = 10_000e6;
        isBuy[2] = false; amts[2] = 5e18;
        isBuy[3] = false; amts[3] = 4e18;
        (uint256[] memory uniOut,,) = _simulateUniV2(INIT_WETH, INIT_USDC, isBuy, amts);

        emit log("--- UniV2 comparison ---");
        emit log_named_uint("UniV2 buyer1 WETH", uniOut[0]);
        emit log_named_uint("UniV2 buyer2 WETH", uniOut[1]);
        emit log_named_uint("UniV2 seller1 USDC", uniOut[2]);
        emit log_named_uint("UniV2 seller2 USDC", uniOut[3]);
    }
}

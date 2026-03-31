// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract FBAMM is ERC20 {
    // ── Token pair ──────────────────────────────────────────────────
    address public immutable token0;
    address public immutable token1;

    // ── LP reserves ─────────────────────────────────────────────────
    uint256 public reserve0;
    uint256 public reserve1;

    // ── Batch auction accumulators (swap/clear — implemented later) ─
    uint256 public Qb; // buy accumulator
    uint256 public Qs; // sell accumulator

    // ── Pending fees (distributed at clearing) ──────────────────────
    uint256 public pendingFees0;
    uint256 public pendingFees1;

    // ── Clearing state ──────────────────────────────────────────────
    uint256 public lastClearedBlock;

    mapping(address => uint256) public batchBuyOrders;
    mapping(address => uint256) public batchSellOrders;
    address[] public batchBuyers;
    address[] public batchSellers;

    // ── Constants ───────────────────────────────────────────────────
    uint256 public constant FEE_BPS = 30;
    uint256 public constant LP_FEE_SHARE = 80;
    uint256 public constant CLEARING_FEE_SHARE = 20;
    uint256 public constant MINIMUM_LIQUIDITY = 1000;

    address private constant DEAD = address(0xdead);

    // ── Constructor ─────────────────────────────────────────────────
    constructor(address _token0, address _token1) ERC20("FBAMM LP", "FBAMM-LP") {
        require(_token0 != address(0) && _token1 != address(0), "zero address");
        require(_token0 != _token1, "identical tokens");
        token0 = _token0;
        token1 = _token1;
    }

    // ── Liquidity ───────────────────────────────────────────────────

    function addLiquidity(uint256 amount0, uint256 amount1) external returns (uint256 lpTokens) {
        require(amount0 > 0 && amount1 > 0, "zero amounts");

        uint256 _totalSupply = totalSupply();

        if (_totalSupply == 0) {
            lpTokens = _sqrt(amount0 * amount1) - MINIMUM_LIQUIDITY;
            _mint(DEAD, MINIMUM_LIQUIDITY);
        } else {
            uint256 lp0 = (amount0 * _totalSupply) / reserve0;
            uint256 lp1 = (amount1 * _totalSupply) / reserve1;
            lpTokens = lp0 < lp1 ? lp0 : lp1;
        }

        require(lpTokens > 0, "insufficient liquidity minted");

        IERC20(token0).transferFrom(msg.sender, address(this), amount0);
        IERC20(token1).transferFrom(msg.sender, address(this), amount1);

        reserve0 += amount0;
        reserve1 += amount1;

        _mint(msg.sender, lpTokens);
    }

    function removeLiquidity(uint256 lpAmount) external returns (uint256 amount0, uint256 amount1) {
        require(lpAmount > 0, "zero amount");

        uint256 _totalSupply = totalSupply();
        amount0 = (lpAmount * reserve0) / _totalSupply;
        amount1 = (lpAmount * reserve1) / _totalSupply;

        require(amount0 > 0 && amount1 > 0, "insufficient liquidity burned");

        _burn(msg.sender, lpAmount);

        reserve0 -= amount0;
        reserve1 -= amount1;

        IERC20(token0).transfer(msg.sender, amount0);
        IERC20(token1).transfer(msg.sender, amount1);
    }

    // ── Swap (batch queuing) ──────────────────────────────────────────

    function swap(address tokenIn, uint256 amountIn) external {
        require(tokenIn == token0 || tokenIn == token1, "invalid token");
        require(amountIn > 0, "zero amount");
        require(reserve0 > 0 && reserve1 > 0, "no liquidity");

        IERC20(tokenIn).transferFrom(msg.sender, address(this), amountIn);

        uint256 fee = (amountIn * FEE_BPS) / 10000;
        uint256 netAmount = amountIn - fee;

        if (tokenIn == token1) {
            // Buying token0 with token1
            pendingFees1 += fee;
            Qb += netAmount;
            if (batchBuyOrders[msg.sender] == 0) {
                batchBuyers.push(msg.sender);
            }
            batchBuyOrders[msg.sender] += netAmount;
        } else {
            // Selling token0 for token1
            pendingFees0 += fee;
            Qs += netAmount;
            if (batchSellOrders[msg.sender] == 0) {
                batchSellers.push(msg.sender);
            }
            batchSellOrders[msg.sender] += netAmount;
        }
    }

    // ── Clear (netting + AMM + distribution) ─────────────────────────

    function clear() external {
        require(lastClearedBlock != block.number, "ALREADY_CLEARED");
        require(Qb > 0 || Qs > 0, "EMPTY_BATCH");

        lastClearedBlock = block.number;

        uint256 _Qb = Qb;
        uint256 _Qs = Qs;

        // AMM interaction for net demand
        uint256 amountOut;
        if (_Qb > _Qs) {
            uint256 netDemand = _Qb - _Qs;
            amountOut = (netDemand * reserve0) / (reserve1 + netDemand);
            reserve1 += netDemand;
            reserve0 -= amountOut;
        } else if (_Qs > _Qb) {
            uint256 netDemand = _Qs - _Qb;
            amountOut = (netDemand * reserve1) / (reserve0 + netDemand);
            reserve0 += netDemand;
            reserve1 -= amountOut;
        }

        // Calculate total output for each side
        uint256 totalToken0ForBuyers;
        uint256 totalToken1ForSellers;

        if (_Qb >= _Qs) {
            // Buy excess or balanced
            totalToken0ForBuyers = _Qs + amountOut; // sellers' token0 + AMM output
            totalToken1ForSellers = _Qs; // matched portion of buyers' token1
        } else {
            // Sell excess
            totalToken0ForBuyers = _Qb; // matched portion of sellers' token0
            totalToken1ForSellers = _Qb + amountOut; // buyers' token1 + AMM output
        }

        // Distribute to buyers (they receive token0)
        if (_Qb > 0) {
            for (uint256 i = 0; i < batchBuyers.length; i++) {
                address buyer = batchBuyers[i];
                uint256 share = batchBuyOrders[buyer];
                uint256 payout = (share * totalToken0ForBuyers) / _Qb;
                if (payout > 0) IERC20(token0).transfer(buyer, payout);
                delete batchBuyOrders[buyer];
            }
        }

        // Distribute to sellers (they receive token1)
        if (_Qs > 0) {
            for (uint256 i = 0; i < batchSellers.length; i++) {
                address seller = batchSellers[i];
                uint256 share = batchSellOrders[seller];
                uint256 payout = (share * totalToken1ForSellers) / _Qs;
                if (payout > 0) IERC20(token1).transfer(seller, payout);
                delete batchSellOrders[seller];
            }
        }

        // Fee distribution: 80% to LP reserves, 20% to clearer
        uint256 lpFee0 = (pendingFees0 * LP_FEE_SHARE) / 100;
        uint256 lpFee1 = (pendingFees1 * LP_FEE_SHARE) / 100;
        uint256 clearerFee0 = pendingFees0 - lpFee0;
        uint256 clearerFee1 = pendingFees1 - lpFee1;

        reserve0 += lpFee0;
        reserve1 += lpFee1;

        if (clearerFee0 > 0) IERC20(token0).transfer(msg.sender, clearerFee0);
        if (clearerFee1 > 0) IERC20(token1).transfer(msg.sender, clearerFee1);

        // Reset batch state
        Qb = 0;
        Qs = 0;
        pendingFees0 = 0;
        pendingFees1 = 0;
        delete batchBuyers;
        delete batchSellers;
    }

    // ── Internal helpers ────────────────────────────────────────────

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

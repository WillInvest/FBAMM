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

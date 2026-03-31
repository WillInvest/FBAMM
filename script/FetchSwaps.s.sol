// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Script.sol";

interface IUniswapV2Pair {
    function getReserves() external view returns (uint112, uint112, uint32);
    function token0() external view returns (address);
    function token1() external view returns (address);
}

contract FetchSwaps is Script {
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

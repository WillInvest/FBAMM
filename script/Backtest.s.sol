// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Script.sol";
import "../src/FBAMM.sol";

/// @notice Placeholder for on-chain backtest integration.
/// The primary backtest is run via analysis/backtest.py which
/// simulates FBAMM clearing in Python for speed.
/// This script can be extended to use Anvil fork + cast for
/// on-chain verification of specific blocks.
contract Backtest is Script {
    function run() external view {
        console.log("Use analysis/backtest.py for full backtest");
        console.log("This script is for on-chain verification of specific blocks");
    }
}

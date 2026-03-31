"""Fetch Uniswap V2 swap events for a block range via RPC eth_getLogs."""

import json
import os
import sys
from urllib.request import Request, urlopen

SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"

POOLS = {
    "ETH_USDC": "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc",
    "ETH_USDT": "0x0d4a11d5EEaaC28EC3F61d100daF4d40471f1852",
    "ETH_WBTC": "0xBb2b8038a1640196FbE3e38816F3e67Cba72D940",
}


def rpc_call(url, method, params):
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1})
    req = Request(url, data=body.encode(), headers={"Content-Type": "application/json"})
    with urlopen(req) as resp:
        return json.loads(resp.read())["result"]


def fetch_swaps(rpc_url, pool_address, from_block, to_block):
    logs = rpc_call(rpc_url, "eth_getLogs", [{
        "address": pool_address,
        "topics": [SWAP_TOPIC],
        "fromBlock": hex(from_block),
        "toBlock": hex(to_block),
    }])

    swaps = []
    for log in logs:
        data = bytes.fromhex(log["data"][2:])
        amount0In = int.from_bytes(data[0:32], "big")
        amount1In = int.from_bytes(data[32:64], "big")
        amount0Out = int.from_bytes(data[64:96], "big")
        amount1Out = int.from_bytes(data[96:128], "big")
        swaps.append({
            "blockNumber": int(log["blockNumber"], 16),
            "txHash": log["transactionHash"],
            "sender": "0x" + log["topics"][1][-40:],
            "to": "0x" + log["topics"][2][-40:],
            "amount0In": str(amount0In),
            "amount1In": str(amount1In),
            "amount0Out": str(amount0Out),
            "amount1Out": str(amount1Out),
        })
    return swaps


def fetch_reserves(rpc_url, pool_address, block_number):
    result = rpc_call(rpc_url, "eth_call", [
        {"to": pool_address, "data": "0x0902f1ac"},
        hex(block_number),
    ])
    data = bytes.fromhex(result[2:])
    r0 = int.from_bytes(data[0:32], "big")
    r1 = int.from_bytes(data[32:64], "big")
    return r0, r1


def main():
    rpc_url = os.environ.get("MAINNET_RPC_URL")
    if not rpc_url:
        print("Set MAINNET_RPC_URL env var", file=sys.stderr)
        sys.exit(1)

    pool_name = sys.argv[1] if len(sys.argv) > 1 else "ETH_USDC"
    from_block = int(sys.argv[2]) if len(sys.argv) > 2 else 19000000
    to_block = int(sys.argv[3]) if len(sys.argv) > 3 else 19000100

    pool_address = POOLS[pool_name]
    print(f"Fetching swaps for {pool_name} ({pool_address}) blocks {from_block}-{to_block}")

    swaps = fetch_swaps(rpc_url, pool_address, from_block, to_block)
    print(f"Found {len(swaps)} swaps")

    blocks = {}
    for swap in swaps:
        bn = swap["blockNumber"]
        if bn not in blocks:
            r0, r1 = fetch_reserves(rpc_url, pool_address, bn - 1)
            blocks[bn] = {"blockNumber": bn, "reserve0": str(r0), "reserve1": str(r1), "swaps": []}
        blocks[bn]["swaps"].append(swap)

    output = {"pool": pool_name, "address": pool_address, "blocks": list(blocks.values())}

    os.makedirs("data", exist_ok=True)
    out_path = f"data/{pool_name}_{from_block}_{to_block}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()

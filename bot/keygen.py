"""
keygen.py - Lighter DEX API Key Generator
Generates a cryptographic API Key pair compatible with Lighter zk-rollup.
"""

import lighter


def generate_keys():
    print("=" * 65)
    print("LIGHTER DEX API KEY GENERATOR")
    print("=" * 65)
    priv, pub, err = lighter.create_api_key()
    if err:
        print(f"[!] Error generating key: {err}")
        return

    print("\n[+] Cryptographic API Key Pair Generated Successfully:")
    print("-" * 65)
    print(f"API Private Key (KEEP SECRET!) : {priv}")
    print(f"API Public Key (Register on DEX) : {pub}")
    print("-" * 65)
    print("\nHow to activate on Lighter DEX:")
    print("1. Go to https://lighter.xyz and connect your Ethereum wallet.")
    print("2. Navigate to Account Settings -> API Management.")
    print("3. Register your Public Key.")
    print("4. Set your Account Index and Private Key in bot/config.py or as environment variables:")
    print(f"   set LIGHTER_ACCOUNT_INDEX=<your_account_index>")
    print(f"   set LIGHTER_PRIVATE_KEY={priv}")
    print("=" * 65)


if __name__ == "__main__":
    generate_keys()

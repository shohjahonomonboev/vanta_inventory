
# currency_converter.py
# A mini-project to practice using a third-party API in Python.
#
# Features:
# - Fetches live FX rates from a public API (no key required)
# - Converts between any two currencies with an amount
# - Simple caching to avoid hitting the API repeatedly
# - Graceful error handling + basic validation
#
# Usage (interactive):
#   python currency_converter.py
#
# Optional flags (non-interactive):
#   python currency_converter.py --from USD --to UZS --amount 25
#   python currency_converter.py --list
#
# Dependencies:
#   pip install requests

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, Tuple

try:
    import requests  # type: ignore
except ImportError:
    print("Missing dependency: requests. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

# --- Config ---
API_URL = "https://api.exchangerate-api.com/v4/latest/USD"  # free endpoint (base USD)
CACHE_FILE = Path(__file__).with_name("rates_cache.json")
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours

COMMON_CODES = [
    "USD","EUR","GBP","AED","SAR","KWD","QAR","OMR",
    "UZS","KZT","RUB","INR","PKR","TRY","CNY","JPY",
]

# --- Helpers ---
def load_cache() -> Tuple[Dict[str, float], float]:
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            rates = data.get("rates", {})
            ts = data.get("timestamp", 0)
            if isinstance(rates, dict) and isinstance(ts, (int, float)):
                return rates, float(ts)
        except Exception:
            pass
    return {}, 0.0

def save_cache(rates: Dict[str, float]) -> None:
    payload = {"rates": rates, "timestamp": time.time()}
    CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch_rates(force_refresh: bool = False) -> Dict[str, float]:
    # Try cache first
    cached_rates, ts = load_cache()
    if cached_rates and not force_refresh and (time.time() - ts) < CACHE_TTL_SECONDS:
        return cached_rates

    # Fetch from API
    try:
        resp = requests.get(API_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rates = data.get("rates")
        if not isinstance(rates, dict):
            raise ValueError("API returned unexpected format")
        save_cache(rates)
        return rates
    except requests.RequestException as e:
        if cached_rates:
            print("Warning: API request failed; using cached rates.", file=sys.stderr)
            return cached_rates
        raise SystemExit(f"Network/API error and no cache available: {e}")

def validate_code(code: str, rates: Dict[str, float]) -> str:
    code = (code or "").upper().strip()
    if code in rates:
        return code
    raise SystemExit(f"Unknown currency code: {code}. Try --list to see common codes.")

def convert(amount: float, from_code: str, to_code: str, rates: Dict[str, float]) -> float:
    # Rates are relative to USD. Convert FROM -> USD -> TO.
    if from_code == to_code:
        return amount
    try:
        rate_from = rates[from_code]
        rate_to = rates[to_code]
    except KeyError:
        raise SystemExit(f"Missing rates for {from_code} or {to_code}. Try different codes.")
    amount_usd = amount / rate_from
    return amount_usd * rate_to

def interactive_flow():
    rates = fetch_rates()
    print("Common currency codes:", ", ".join(COMMON_CODES))
    print("Tip: You can also run with flags. Example: --from USD --to UZS --amount 25")
    try:
        from_code = validate_code(input("From currency code (e.g., USD): "), rates)
        to_code = validate_code(input("To currency code (e.g., UZS): "), rates)
        amount = float(input("Amount: "))
    except ValueError:
        raise SystemExit("Invalid amount. Please enter a number.")
    result = convert(amount, from_code, to_code, rates)
    print(f"\n{amount:.4f} {from_code} = {result:.4f} {to_code}")

def main():
    parser = argparse.ArgumentParser(description="Currency converter using a third-party API")
    parser.add_argument("--from", dest="from_code", help="Source currency code, e.g., USD")
    parser.add_argument("--to", dest="to_code", help="Target currency code, e.g., UZS")
    parser.add_argument("--amount", type=float, help="Amount to convert")
    parser.add_argument("--refresh", action="store_true", help="Force refresh rates (ignore cache)")
    parser.add_argument("--list", action="store_true", help="List common currency codes and exit")
    args = parser.parse_args()

    if args.list:
        print("Common currency codes:", ", ".join(COMMON_CODES))
        sys.exit(0)

    rates = fetch_rates(force_refresh=args.refresh)

    if args.from_code and args.to_code and args.amount is not None:
        from_code = validate_code(args.from_code, rates)
        to_code = validate_code(args.to_code, rates)
        result = convert(args.amount, from_code, to_code, rates)
        print(f"{args.amount:.4f} {from_code} = {result:.4f} {to_code}")
    else:
        interactive_flow()

if __name__ == "__main__":
    main()

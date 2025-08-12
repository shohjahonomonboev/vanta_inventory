
# Currency Converter (Third-Party API Mini-Project)

A hands-on practice project to learn how to call and use a **third-party API** from Python.

**What it does**
- Fetches live FX rates from a free public API (base = USD).
- Converts between any two currencies.
- Caches results locally for 24h to reduce API calls.
- Works in interactive mode or via CLI flags.

## Requirements
- Python 3.9+
- Install dependency:
  ```bash
  pip install requests
  ```

## Run (Interactive)
```bash
python currency_converter.py
```

## Run (Non-Interactive)
```bash
python currency_converter.py --from USD --to UZS --amount 25
python currency_converter.py --from AED --to USD --amount 100
python currency_converter.py --list
```

## How it uses a Third-Party API
- Endpoint: `https://api.exchangerate-api.com/v4/latest/USD`
- Your code sends an **HTTP GET** request and receives **JSON**.
- JSON contains a `rates` dict with codes → rate vs USD.
- Conversion formula: `amount_in_usd = amount / rates[from]` then `* rates[to]`.

## Next steps (Vanta integration idea)
- Move fetching into a Flask route `/rates` with caching.
- Add a front-end dropdown for currencies; convert prices dynamically.
- Optionally switch to a provider with hourly updates.

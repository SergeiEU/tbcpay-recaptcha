# TBCPay reCAPTCHA Solver

Get reCAPTCHA v3 tokens from TBCPay and check your utility bills in Tbilisi.


## What it does

- Grabs reCAPTCHA v3 tokens from TBCPay website
- Makes checking multiple bills way faster

## Setup

```bash
pip install zendriver requests
```

That's it. Zendriver handles the browser automation part.

## Basic usage

### Checking water bill

```python
import asyncio
from tbcpay_recaptcha import TBCPayService

async def main():
    service = TBCPayService(
        service_id=2758,
        service_name="Tbilisi Water"
    )

    result = await service.check_balance_async("YOUR_ACCOUNT_NUMBER")
    print(result)

    await service.close()

asyncio.run(main())
```

### Checking electricity

```python
import asyncio
from tbcpay_recaptcha import TBCPayService

async def main():
    service = TBCPayService(
        service_id=771,
        service_name="Tbilisi Energy"
    )

    result = await service.check_balance_async("YOUR_ACCOUNT_NUMBER")
    print(result)

    await service.close()

asyncio.run(main())
```

## Running the examples

```bash
python examples/example_water.py YOUR_ACCOUNT_NUMBER
python examples/example_electricity.py YOUR_ACCOUNT_NUMBER
```

## Adding other services

You need two things:
1. The service ID from TBCPay
2. Whether it uses step 1 or 2 (most use 2)

### Finding service IDs

Open tbcpay.ge, go to your service, open browser devtools (F12), check the Network tab, and look for `GetNextSteps` requests. The service ID is right there in the payload.

Here's what I've found so far:

| Service | ID | Step |
|---------|-----|------|
| Tbilisi Water | 2758 | 2 |
| Tbilisi Energy | 771 | 2 |
| TELMICO | 2817 | 2 |
| Tbilservice Group | 765 | 2 |
| CityCom | 915 | 1 |

### Example for a new service

```python
import asyncio
from tbcpay_recaptcha import TBCPayService

async def check_balance():
    service = TBCPayService(
        service_id=YOUR_SERVICE_ID,
        service_name="Whatever Service",
        headless=True
    )

    result = await service.check_balance_async(
        account_id="YOUR_ACCOUNT",
        step_order=2
    )

    if result['status'] == 'success':
        print(f"Balance: {result['balance']} {result['currency']}")
        print(f"Name: {result['customer_name']}")
        print(f"To pay: {result['amount_to_pay']}")
    else:
        print(f"Error: {result['error']}")

    await service.close()

asyncio.run(check_balance())
```

## How it works

The `RecaptchaSolver` class:
- Starts a browser instance using zendriver
- Loads the TBCPay page once
- Executes the reCAPTCHA JavaScript to get tokens
- Caches tokens for 110 seconds (they're valid for ~2 minutes)

The `TBCPayService` class:
- Manages the solver instance
- Makes API requests to TBCPay
- Parses the responses into something usable

## Response format

When everything works:

```python
{
    'account_id': '123456',
    'service': 'Tbilisi Water',
    'status': 'success',
    'customer_name': 'John Doe',
    'balance': 0.0,
    'amount_to_pay': 0.0,
    'currency': 'GEL',
    'can_pay': True,
    'raw_data': {...}
}
```

When something breaks:

```python
{
    'account_id': '123456',
    'service': 'Tbilisi Water',
    'status': 'error',
    'error': 'Request timeout'
}
```

## Requirements

- Python 3.7 or newer
- zendriver
- requests

## License

MIT. Do whatever you want with it.

## Notes

This is for personal use. Don't abuse TBCPay's API or you might get rate limited. Also, account numbers and tokens are sensitive - don't commit them to git or share them publicly.

Check out SERVICES.md if you want more details on adding new services.

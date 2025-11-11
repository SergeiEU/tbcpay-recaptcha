# Adding New Services

Want to check other utility bills? Here's how.

## What you need

Just two things:
1. **Service ID** - a number TBCPay uses to identify the service
2. **Step order** - usually 2, sometimes 1

## Finding the service ID

This is the annoying part, but it only takes a minute:

1. Go to tbcpay.ge
2. Find your service and enter your account number
3. Open browser devtools (F12)
4. Go to Network tab
5. Click through to the next step
6. Look for a request called `GetNextSteps`
7. Click on it and check the Payload/Request section
8. You'll see `"serviceId": 2758` or something like that

That number is what you need.

## Quick template

```python
import asyncio
from tbcpay_recaptcha import TBCPayService

async def check_my_service():
    service = TBCPayService(
        service_id=1234,  # put your service ID here
        service_name="My Service"
    )

    result = await service.check_balance_async(
        account_id="YOUR_ACCOUNT",
        step_order=2  # try 2 first, if it fails try 1
    )

    print(result)
    await service.close()

asyncio.run(check_my_service())
```

## Services I know about

| Service | ID | Step | Notes |
|---------|-----|------|-------|
| Tbilisi Water | 2758 | 2 | Works fine |
| Tbilisi Energy | 771 | 2 | Works fine |
| TELMICO | 2817 | 2 | Sometimes slow |
| Tbilservice Group | 765 | 2 | Works fine |
| CityCom | 915 | 1 | Different step! |

If you find more, let me know or submit a PR.

## Understanding the parameters

### service_id
This is just TBCPay's internal identifier. Every service has one. You can't guess it, you have to find it in the network requests.

### service_name
Whatever you want to call it. This is just for display purposes in your code.

### step_order
Most services use step 2. CityCom uses step 1 for some reason. If you get weird errors or empty responses, try switching between 1 and 2.

## What you get back

Success looks like:

```python
{
    'status': 'success',
    'balance': 0.0,
    'amount_to_pay': 0.0,
    'customer_name': 'John Doe',
    'currency': 'GEL',
    'can_pay': True
}
```

Errors look like:

```python
{
    'status': 'error',
    'error': 'whatever went wrong'
}
```

## Example: Adding gas service

Let's say you found gas service has ID 2900. Here's how you'd check it:

```python
import asyncio
from tbcpay_recaptcha import TBCPayService

async def check_gas():
    service = TBCPayService(
        service_id=2900,
        service_name="Gas Service"
    )

    try:
        result = await service.check_balance_async(
            account_id="1234567",
            step_order=2
        )

        if result['status'] == 'success':
            print(f"Customer: {result['customer_name']}")
            print(f"Balance: {result['balance']} GEL")
            if result['amount_to_pay'] > 0:
                print(f"You owe: {result['amount_to_pay']} GEL")
            else:
                print("All paid up")
        else:
            print(f"Something broke: {result['error']}")

    finally:
        await service.close()

asyncio.run(check_gas())
```

## Common issues

### "Invalid response format"
Try changing step_order from 2 to 1 or vice versa.

### "Failed to get reCAPTCHA token"
Check your internet. Make sure zendriver is installed.

### "Request timeout"
The service might be slow. Or your service ID is wrong.

### Wrong data
Double check the service ID. Look at `raw_data` in the response to see what you're actually getting.

## Tips

- Save the response's `raw_data` field when debugging - it shows exactly what TBCPay sends back
- If step 2 doesn't work, try step 1
- Some services are just slow, especially TELMICO
- The browser takes a few seconds to start the first time, that's normal

## Found a new service?

Add it to the table above and submit a PR. Or just open an issue with the service name and ID.

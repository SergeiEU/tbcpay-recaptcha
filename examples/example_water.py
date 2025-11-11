#!/usr/bin/env python3
"""
Example: Checking Tbilisi Water balance

This example demonstrates how to check water utility balance using TBCPayService.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tbcpay_recaptcha import TBCPayService


async def check_water_balance(account_number: str):
    """
    Check water utility balance for Tbilisi Water (GWP).

    Args:
        account_number: Your water account number (customer code)
    """
    # Service configuration for Tbilisi Water
    SERVICE_ID = 2758  # TBCPay service ID for Tbilisi Water
    SERVICE_NAME = "Tbilisi Water"

    print(f"Checking {SERVICE_NAME} balance...")
    print(f"Account: {account_number}")
    print("-" * 50)

    # Initialize service
    service = TBCPayService(
        service_id=SERVICE_ID,
        service_name=SERVICE_NAME,
        headless=True  # Run browser in headless mode
    )

    try:
        # Check balance
        result = await service.check_balance_async(
            account_id=account_number,
            step_order=2  # Tbilisi Water uses step 2
        )

        # Display results
        if result['status'] == 'success':
            print("✓ Success!")
            print(f"  Customer: {result['customer_name']}")
            print(f"  Balance: {result['balance']:.2f} {result['currency']}")
            print(f"  Amount to pay: {result['amount_to_pay']:.2f} {result['currency']}")

            if result['balance'] <= 0:
                print("  Status: ✓ Paid (or overpaid)")
            else:
                print(f"  Status: ✗ Debt: {result['amount_to_pay']:.2f} {result['currency']}")
        else:
            print(f"✗ Error: {result['error']}")

    finally:
        # Clean up
        await service.close()


if __name__ == "__main__":
    # Replace with your account number
    ACCOUNT_NUMBER = "123456789"

    if len(sys.argv) > 1:
        ACCOUNT_NUMBER = sys.argv[1]

    print("=" * 50)
    print("Tbilisi Water Balance Checker")
    print("=" * 50)
    print()

    asyncio.run(check_water_balance(ACCOUNT_NUMBER))

"""
Base class for checking utility bills via TBCPay API.

Handles the token stuff and API requests so you don't have to deal with it.
"""

import requests
from typing import Dict, Optional
from .solver import RecaptchaSolver


class TBCPayService:
    """
    Checks utility bills through TBCPay.

    Takes care of getting reCAPTCHA tokens, making API calls,
    and turning the responses into something you can actually use.
    """

    API_BASE_URL = "https://api.tbcpay.ge"

    def __init__(self, service_id: int, service_name: str, headless: bool = True):
        """
        service_id: the number TBCPay uses for this service
        service_name: whatever you want to call it
        headless: hide the browser window
        """
        self.service_id = service_id
        self.service_name = service_name
        self.headless = headless
        self._solver = None

        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Clientid': 'Web',
            'Origin': 'https://tbcpay.ge',
            'Referer': 'https://tbcpay.ge/',
            'Accept-Language': 'en-US,en;q=0.9',
            'Lang': 'en-US',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        })

    async def _ensure_solver(self):
        """Start the solver if it's not running yet."""
        if self._solver is None:
            self._solver = RecaptchaSolver(headless=self.headless)
            await self._solver.start()

    async def get_token_async(self) -> Optional[str]:
        """Gets a reCAPTCHA token (might use cached one)."""
        await self._ensure_solver()
        return await self._solver.get_token(action="payment")

    async def check_balance_async(
        self,
        account_id: str,
        step_order: int = 2
    ) -> Dict:
        """
        Checks your account balance.

        account_id: your account number
        step_order: usually 2, but CityCom uses 1 for some reason
        """
        try:
            # Get reCAPTCHA token
            token = await self.get_token_async()
            if not token:
                return {
                    'account_id': account_id,
                    'service': self.service_name,
                    'status': 'error',
                    'error': 'Failed to get reCAPTCHA token'
                }

            # Make API request
            url = f"{self.API_BASE_URL}/api/Service/GetNextSteps"
            payload = {
                "context": [
                    {"key": "ROOT_SERVICE_ID", "value": str(self.service_id)},
                    {"key": "abonentCode", "value": str(account_id)}
                ],
                "recaptchaToken": token,
                "serviceId": self.service_id,
                "stepOrder": step_order,
                "origin": "Payment"
            }

            response = self.session.post(url, json=payload, timeout=15)

            if response.status_code == 200:
                data = response.json()

                if data.get('success') and data.get('data'):
                    return self._parse_response(data, account_id)
                else:
                    error_msg = self._extract_error(data)
                    return {
                        'account_id': account_id,
                        'service': self.service_name,
                        'status': 'error',
                        'error': error_msg
                    }
            else:
                return {
                    'account_id': account_id,
                    'service': self.service_name,
                    'status': 'error',
                    'error': f'HTTP {response.status_code}'
                }

        except requests.exceptions.Timeout:
            return {
                'account_id': account_id,
                'service': self.service_name,
                'status': 'error',
                'error': 'Request timeout'
            }
        except Exception as e:
            return {
                'account_id': account_id,
                'service': self.service_name,
                'status': 'error',
                'error': str(e)
            }

    def _parse_response(self, data: Dict, account_id: str) -> Dict:
        """
        Parse API response and extract balance information.

        Args:
            data: API response data
            account_id: Account number

        Returns:
            Parsed balance information
        """
        step_data = data['data'].get('step', {})
        step_params = step_data.get('stepParameters', [])

        if not isinstance(step_params, list):
            return {
                'account_id': account_id,
                'service': self.service_name,
                'status': 'error',
                'error': 'Invalid response format'
            }

        # Convert parameters to dict
        params = {p['key']: p.get('value', '') for p in step_params}

        # Extract balance
        try:
            debt = float(params.get('DEBT', 0))
            debt_amount = float(params.get('DebtAmount', debt))
        except ValueError:
            debt = 0.0
            debt_amount = 0.0

        # Extract customer name
        name = params.get('CLIENTINFO') or params.get('NAME') or params.get('customerName') or 'N/A'

        return {
            'account_id': params.get('abonentCode', account_id),
            'service': self.service_name,
            'status': 'success',
            'customer_name': name,
            'balance': debt,
            'amount_to_pay': abs(debt_amount) if debt > 0 else 0,
            'currency': params.get('DebtCurrency', 'GEL'),
            'can_pay': params.get('CANPAY') == '1',
            'raw_data': params
        }

    def _extract_error(self, data: Dict) -> str:
        """Extract error message from API response."""
        if data.get('errors'):
            errors = data['errors']
            if isinstance(errors, list):
                return '; '.join([
                    e.get('message', str(e)) if isinstance(e, dict) else str(e)
                    for e in errors
                ])
            return str(errors)
        return 'Unknown error'

    async def close(self):
        """Close the solver and release resources."""
        if self._solver:
            await self._solver.stop()
            self._solver = None

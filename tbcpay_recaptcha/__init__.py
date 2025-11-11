"""
TBCPay reCAPTCHA Solver

A Python library for obtaining reCAPTCHA v3 tokens from TBCPay website
and checking utility bills balances in Tbilisi, Georgia.
"""

from .solver import RecaptchaSolver, get_recaptcha_token
from .service import TBCPayService

__version__ = "1.0.0"
__all__ = ["RecaptchaSolver", "get_recaptcha_token", "TBCPayService"]

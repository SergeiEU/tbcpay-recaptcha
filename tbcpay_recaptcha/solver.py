"""
Gets reCAPTCHA v3 tokens from TBCPay using Zendriver.

Caches tokens for ~2 minutes and keeps the browser open so you don't have to
start it over and over.
"""

import asyncio
import logging
import time
from typing import Optional

try:
    import zendriver as zd
except ImportError:
    zd = None

logger = logging.getLogger(__name__)


class RecaptchaSolver:
    """
    Handles reCAPTCHA token generation for TBCPay.

    Keeps the browser open and caches tokens so you don't waste time
    restarting everything for each request.
    """

    TBCPAY_URL = "https://tbcpay.ge"
    RECAPTCHA_SITE_KEY = "6LeYsrYZAAAAAMhY05m7_AIPPftm2v0AgNl2nloP"
    TOKEN_LIFETIME = 110  # tokens last about 2 minutes, use 110s to be safe
    TIMEOUT = 30

    def __init__(self, headless: bool = True):
        """
        headless: whether to show the browser window (True = hidden)
        """
        if zd is None:
            raise ImportError("zendriver not installed - run: pip install zendriver")

        self.headless = headless
        self.browser = None
        self.page = None
        self._last_token = None
        self._token_timestamp = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()

    async def start(self):
        """Starts the browser and loads TBCPay page."""
        logger.info("Starting browser...")
        self.browser = await zd.start(headless=self.headless)
        logger.info("Browser started")

        # Load TBCPay page once
        logger.info(f"Loading {self.TBCPAY_URL}...")
        self.page = await self.browser.get(self.TBCPAY_URL)
        await asyncio.sleep(3)  # give reCAPTCHA time to initialize
        logger.info("Ready")

    async def stop(self):
        """Stop the browser instance."""
        if self.browser:
            logger.info("Stopping browser...")
            await self.browser.stop()
            self.browser = None
            self.page = None
            self._last_token = None
            self._token_timestamp = None

    async def get_token(self, action: str = "payment", force_new: bool = False) -> Optional[str]:
        """
        Gets a reCAPTCHA token. Uses cached one if it's still fresh.

        action: what to put in the reCAPTCHA action field (usually "payment")
        force_new: get a new token even if cached one is still valid
        """
        if not self.browser or not self.page:
            raise RuntimeError("Browser not started - call start() first")

        # use cached token if it's still good
        if not force_new and self._is_token_valid():
            age = int(time.time() - self._token_timestamp)
            logger.info(f"Using cached token ({age}s old)")
            return self._last_token

        try:
            logger.info("Getting fresh token...")

            # Execute reCAPTCHA and get token using CDP
            execute_script = f"""
            (async () => {{
                // Wait for grecaptcha.execute to be available
                for (let i = 0; i < 60; i++) {{
                    if (typeof grecaptcha !== 'undefined' && typeof grecaptcha.execute === 'function') {{
                        break;
                    }}
                    await new Promise(r => setTimeout(r, 500));
                }}

                if (typeof grecaptcha === 'undefined' || typeof grecaptcha.execute !== 'function') {{
                    throw new Error('grecaptcha.execute not available');
                }}

                // Execute reCAPTCHA
                const token = await grecaptcha.execute('{self.RECAPTCHA_SITE_KEY}', {{action: '{action}'}});
                return token;
            }})()
            """

            # Use CDP Runtime.evaluate for proper Promise handling
            cdp_result = await self.page.send(zd.cdp.runtime.evaluate(
                expression=execute_script,
                await_promise=True,
                return_by_value=True
            ))

            # CDP returns tuple (result, exception)
            result, exception = cdp_result if isinstance(cdp_result, tuple) else (cdp_result, None)

            if exception:
                logger.error(f"CDP exception: {exception}")
                return None

            # Extract token from CDP result
            if result and hasattr(result, 'value'):
                token = result.value
                if token and isinstance(token, str):
                    logger.info(f"Successfully obtained reCAPTCHA token (length: {len(token)})")
                    # Cache the token
                    self._last_token = token
                    self._token_timestamp = time.time()
                    return token

            logger.error("Failed to extract token from CDP result")
            return None

        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for reCAPTCHA token after {self.TIMEOUT}s")
            return None

        except Exception as e:
            logger.error(f"Error getting reCAPTCHA token: {e}")
            return None

    def _is_token_valid(self) -> bool:
        """Check if cached token is still valid."""
        if not self._last_token or not self._token_timestamp:
            return False
        age = time.time() - self._token_timestamp
        return age < self.TOKEN_LIFETIME


async def get_recaptcha_token(headless: bool = True, action: str = "payment") -> Optional[str]:
    """
    Convenience function to get a reCAPTCHA token with automatic cleanup.

    Args:
        headless: Run browser in headless mode
        action: The action name for reCAPTCHA

    Returns:
        The reCAPTCHA token or None if failed

    Example:
        >>> import asyncio
        >>> token = asyncio.run(get_recaptcha_token())
        >>> print(f"Token: {token[:50]}...")
    """
    async with RecaptchaSolver(headless=headless) as solver:
        return await solver.get_token(action=action)

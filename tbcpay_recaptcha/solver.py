"""
Gets reCAPTCHA v3 tokens from TBCPay using Zendriver.

Caches tokens for ~2 minutes and keeps the browser open so you don't have to
start it over and over.
"""

import asyncio
import logging
import re
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
    RECAPTCHA_SITE_KEY_FALLBACK = "6LeYsrYZAAAAAMhY05m7_AIPPftm2v0AgNl2nloP"  # fallback if auto-detection fails
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
        self._site_key = self.RECAPTCHA_SITE_KEY_FALLBACK  # start with fallback, auto-detect on error

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

        logger.info("Ready (using fallback site key)")

    async def _detect_site_key(self):
        """Extract reCAPTCHA site key from the page source."""
        try:
            # Method 1: Try to get site key directly from window.grecaptcha
            try:
                js_key = await self.page.send(zd.cdp.runtime.evaluate(
                    expression="""
                    (() => {
                        // Try to find site key in window or grecaptcha object
                        if (window.grecaptcha && window.grecaptcha.enterprise) {
                            return window.grecaptcha.enterprise.sitekey;
                        }
                        // Search in all script tags
                        const scripts = Array.from(document.scripts);
                        for (const script of scripts) {
                            const content = script.innerHTML || script.src;
                            const match = content.match(/6[A-Za-z0-9_-]{38,}/);
                            if (match) return match[0];
                        }
                        return null;
                    })()
                    """,
                    return_by_value=True
                ))

                result, exception = js_key if isinstance(js_key, tuple) else (js_key, None)
                if not exception and result and hasattr(result, 'value') and result.value:
                    key = result.value
                    if len(key) > 30 and key.startswith('6'):
                        self._site_key = key
                        logger.info(f"Auto-detected reCAPTCHA site key from JS: {key[:20]}...")
                        return
            except Exception as e:
                logger.debug(f"JS detection method failed: {e}")

            # Method 2: Parse HTML source
            page_source = await self.page.send(zd.cdp.runtime.evaluate(
                expression="document.documentElement.outerHTML",
                return_by_value=True
            ))

            result, exception = page_source if isinstance(page_source, tuple) else (page_source, None)

            if exception or not result or not hasattr(result, 'value'):
                logger.warning("Failed to get page source for site key detection")
                self._site_key = self.RECAPTCHA_SITE_KEY_FALLBACK
                return

            html = result.value

            # Try multiple patterns to find the site key
            patterns = [
                r'6[A-Za-z0-9_-]{38,}',  # Generic reCAPTCHA key pattern
                r'grecaptcha\.execute\([\'"]([^"\']+)[\'"]',  # grecaptcha.execute('KEY')
                r'data-sitekey=[\'"]([^"\']+)[\'"]',  # data-sitekey="KEY"
                r'sitekey[\'"]?\s*:\s*[\'"]([^"\']+)[\'"]',  # sitekey: "KEY"
                r'render[\'"]?\s*:\s*[\'"]([^"\']+)[\'"]',  # render: "KEY"
            ]

            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    detected_key = match.group(1) if match.lastindex else match.group(0)
                    # Validate format (reCAPTCHA keys start with 6 and are ~40 chars)
                    if len(detected_key) > 30 and detected_key.startswith('6'):
                        self._site_key = detected_key
                        logger.info(f"Auto-detected reCAPTCHA site key from HTML: {detected_key[:20]}...")
                        return

            # If no key found, use fallback
            logger.warning("Could not auto-detect site key, using fallback")
            self._site_key = self.RECAPTCHA_SITE_KEY_FALLBACK

        except Exception as e:
            logger.error(f"Error detecting site key: {e}")
            self._site_key = self.RECAPTCHA_SITE_KEY_FALLBACK

    async def stop(self):
        """Stop the browser instance."""
        if self.browser:
            logger.info("Stopping browser...")
            await self.browser.stop()
            self.browser = None
            self.page = None
            self._last_token = None
            self._token_timestamp = None
            self._site_key = self.RECAPTCHA_SITE_KEY_FALLBACK  # reset to fallback

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

        # Try to get token with current site key
        token = await self._try_get_token(action)

        # If failed and using fallback key, try auto-detecting
        if token is None and self._site_key == self.RECAPTCHA_SITE_KEY_FALLBACK:
            logger.warning("Failed with fallback key, trying to auto-detect site key...")
            await self._detect_site_key()

            # Retry with detected key if it's different
            if self._site_key != self.RECAPTCHA_SITE_KEY_FALLBACK:
                logger.info("Retrying with auto-detected key...")
                token = await self._try_get_token(action)

        return token

    async def _try_get_token(self, action: str) -> Optional[str]:
        """Try to get a reCAPTCHA token with current site key."""
        try:
            logger.info(f"Getting fresh token with site key: {self._site_key[:20]}...")

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
                const token = await grecaptcha.execute('{self._site_key}', {{action: '{action}'}});
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

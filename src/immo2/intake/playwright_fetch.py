"""
Single-URL Playwright fetch. User-triggered only — NOT mass crawl.
Gracefully fails if bot detection blocks access.
"""
from __future__ import annotations
from ..models.listing import RawListing


async def fetch_url(url: str, timeout_ms: int = 30_000) -> RawListing:
    """Fetch a single URL using Playwright and return extracted text.
    User-triggered only. Does NOT store results beyond this call.
    Falls back gracefully if access is blocked.
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="de-DE",
            )
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(2000)  # let JS render

                # Check for bot detection / login walls
                page_text = await page.inner_text("body")
                blocked_signals = [
                    "captcha", "blocked", "403", "access denied",
                    "bitte melden sie sich an", "login required",
                    "bot detection", "cloudflare",
                ]
                if any(sig in page_text.lower() for sig in blocked_signals):
                    await browser.close()
                    return RawListing(
                        raw_text="",
                        source_url=url,
                        source_type="url",
                        ocr_used=False,
                    )

                # Extract structured text: prefer main article content
                raw_text = page_text

                # Image URLs (for future photo analysis)
                image_urls = await page.eval_on_selector_all(
                    "img[src]",
                    "els => els.map(el => el.src).filter(s => s.startsWith('http'))"
                )

                await browser.close()
                return RawListing(
                    raw_text=raw_text,
                    source_url=url,
                    source_type="url",
                    image_urls=image_urls[:20],  # cap at 20 images
                    ocr_used=False,
                )

            except PlaywrightTimeout:
                await browser.close()
                return RawListing(
                    raw_text="",
                    source_url=url,
                    source_type="url",
                )

    except ImportError:
        return RawListing(
            raw_text="",
            source_url=url,
            source_type="url",
        )
    except Exception as e:
        return RawListing(
            raw_text=f"[Fetch failed: {e}]",
            source_url=url,
            source_type="url",
        )

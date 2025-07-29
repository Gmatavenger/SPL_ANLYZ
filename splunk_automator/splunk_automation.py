import re
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from .config import Config
from .screenshot import save_screenshot_to_tmp
from .logging_setup import logger

async def process_single_dashboard(playwright, db_data, start_dt, end_dt, username, password, capture_only=False):
    name = db_data['name']
    logger.info(f"[LOG] Starting analysis for dashboard '{name}'.")
    browser = None
    try:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        is_studio = False
        try:
            await page.wait_for_selector("splunk-dashboard-view", timeout=5_000)
            is_studio = True
        except Exception:
            pass

        param_prefix = "form.global_time" if is_studio else "form.time_field"
        params = {}
        params[f"{param_prefix}.earliest"] = int(start_dt.timestamp()) if not isinstance(start_dt, str) else start_dt
        params[f"{param_prefix}.latest"] = int(end_dt.timestamp()) if not isinstance(end_dt, str) else end_dt
        full_url = f"{db_data['url'].split('?')[0]}?{'&'.join(f'{k}={v}' for k,v in params.items())}"
        await page.goto(full_url, timeout=120_000)

        username_field = page.locator('input[name="username"]')
        if await username_field.is_visible(timeout=5000):
            await username_field.fill(username)
            await page.locator('input[name="password"]').fill(password)
            submit_button = page.locator('button[type="submit"], input[type="submit"]').first
            await submit_button.click()
            try:
                await page.wait_for_url(lambda url: "account/login" not in url, timeout=15000)
            except PlaywrightTimeoutError:
                return False

        filename = f"{re.sub('[^A-Za-z0-9]+', '_', name)}_{datetime.now(Config.EST).strftime('%H%M%S')}.png"
        if is_studio:
            try:
                height = await page.evaluate("""
                    () => {
                        const el = document.querySelector('splunk-dashboard-view');
                        return el ? el.scrollHeight : document.body.scrollHeight;
                    }
                """)
                await page.set_viewport_size({"width": 1280, "height": height})
            except Exception as e:
                logger.warning(f"Could not resize viewport for Studio: {e}")
            screenshot_bytes = await page.screenshot(full_page=True)
        else:
            screenshot_bytes = await page.screenshot(full_page=True)
        save_screenshot_to_tmp(screenshot_bytes, filename)
        logger.info(f"Screenshot for '{name}' saved to tmp/{filename}")
        return True
    except Exception as e:
        logger.error(f"Error processing '{name}': {e}", exc_info=True)
        return False
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
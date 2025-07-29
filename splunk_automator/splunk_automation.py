import re
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from .config import Config
from .screenshot import save_screenshot_to_tmp
from .logging_setup import logger

async def process_single_dashboard(playwright, db_data, start_dt, end_dt, username, password, capture_only=False):
    """Process a single dashboard - login, navigate, wait for load, take screenshot."""
    name = db_data['name']
    logger.info(f"Starting processing for dashboard '{name}' (capture_only={capture_only})")
    browser = None
    
    try:
        # Launch browser
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-extensions',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu'
            ]
        )
        
        # Create context with reasonable settings
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            ignore_https_errors=True,
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        page = await context.new_page()
        
        # Format URL with time parameters
        full_url = format_time_for_url(db_data['url'], start_dt, end_dt)
        logger.info(f"Navigating to: {full_url}")
        
        # Navigate to dashboard
        await page.goto(full_url, timeout=120_000, wait_until='networkidle')
        
        # Handle login if required
        login_success = await handle_splunk_login(page, username, password)
        if not login_success:
            logger.error(f"Login failed for dashboard: {name}")
            return False
        
        # Wait for dashboard to load completely
        load_success = await wait_for_splunk_dashboard_to_load(page, name)
        if not load_success:
            logger.warning(f"Dashboard may not have loaded completely: {name}")
        
        # Take screenshot
        success = await capture_dashboard_screenshot(page, name)
        return success
        
    except Exception as e:
        logger.error(f"Error processing dashboard '{name}': {e}", exc_info=True)
        return False
    finally:
        if browser:
            try:
                await browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")

async def handle_splunk_login(page, username, password):
    """Handle Splunk login if login page is detected."""
    try:
        # Check if we're on a login page
        login_form = page.locator('form[action*="login"], form[action*="account"]')
        username_field = page.locator('input[name="username"], input[id="username"]')
        
        # Wait a moment to see if login form appears
        try:
            await username_field.wait_for(timeout=5000)
            logger.info("Login form detected, attempting login")
        except:
            # No login form found, assume already logged in
            logger.info("No login form detected, proceeding")
            return True
        
        # Fill login form
        await username_field.fill(username)
        password_field = page.locator('input[name="password"], input[id="password"]')
        await password_field.fill(password)
        
        # Submit login
        submit_button = page.locator('button[type="submit"], input[type="submit"]').first
        await submit_button.click()
        
        # Wait for login to complete (URL should change away from login page)
        try:
            await page.wait_for_function(
                'window.location.href.indexOf("login") === -1 && window.location.href.indexOf("account/login") === -1',
                timeout=15000
            )
            logger.info("Login successful")
            return True
        except PlaywrightTimeoutError:
            logger.error("Login timeout - credentials may be incorrect")
            return False
            
    except Exception as e:
        logger.error(f"Login error: {e}")
        return False

async def wait_for_splunk_dashboard_to_load(page, name):
    """Wait for Splunk dashboard panels to load and data to populate."""
    try:
        logger.info(f"Waiting for dashboard to load: {name}")
        
        # First, determine if this is a Studio or Classic dashboard
        is_studio = await detect_dashboard_type(page)
        logger.info(f"Dashboard type detected - Studio: {is_studio}")
        
        if is_studio:
            return await wait_for_studio_dashboard(page, name)
        else:
            return await wait_for_classic_dashboard(page, name)
            
    except Exception as e:
        logger.error(f"Error waiting for dashboard to load ({name}): {e}")
        return False

async def detect_dashboard_type(page):
    """Detect if dashboard is Studio or Classic."""
    try:
        # Look for Studio-specific elements
        await page.wait_for_selector("splunk-dashboard-view, dashboard-view", timeout=10000)
        return True
    except:
        # Look for Classic dashboard elements
        try:
            await page.wait_for_selector(".dashboard-body, #dashboard, .dashboard-element", timeout=5000)
            return False
        except:
            # Default to Classic if can't determine
            return False

async def wait_for_studio_dashboard(page, name):
    """Wait for Studio dashboard to load completely."""
    try:
        # Wait for main dashboard container
        await page.wait_for_selector("splunk-dashboard-view", timeout=30000)
        logger.info(f"Studio dashboard container loaded: {name}")
        
        # Wait for visualizations to appear
        await page.wait_for_function("""
            () => {
                const vizElements = document.querySelectorAll(
                    'splunk-viz, splunk-single-value, splunk-table, splunk-choropleth-map, ' +
                    'splunk-cluster-map, splunk-bubble-chart, splunk-sankey-diagram'
                );
                return vizElements.length > 0;
            }
        """, timeout=30000)
        logger.info(f"Studio visualizations detected: {name}")
        
        # Wait for loading states to complete
        await page.wait_for_function("""
            () => {
                // Check for common loading indicators
                const loadingSelectors = [
                    '[data-test="loading"]',
                    '.loading',
                    '.spinner',
                    '.wait-spinner',
                    '[aria-label*="loading"]',
                    '.viz-loading'
                ];
                
                for (const selector of loadingSelectors) {
                    const elements = document.querySelectorAll(selector);
                    for (const el of elements) {
                        if (el.offsetParent !== null) { // Element is visible
                            return false;
                        }
                    }
                }
                return true;
            }
        """, timeout=60000)
        logger.info(f"Studio loading indicators cleared: {name}")
        
        # Wait for data to populate (look for actual content)
        await page.wait_for_function("""
            () => {
                const vizElements = document.querySelectorAll('splunk-viz, splunk-single-value, splunk-table');
                let hasContent = false;
                
                vizElements.forEach(el => {
                    // Check if element has visible content (not just placeholders)
                    const textContent = el.textContent || '';
                    const hasNumbers = /\d+/.test(textContent);
                    const hasText = textContent.trim().length > 10;
                    
                    if (hasNumbers || hasText) {
                        hasContent = true;
                    }
                });
                
                return hasContent || vizElements.length === 0; // Pass if no viz elements
            }
        """, timeout=45000)
        logger.info(f"Studio dashboard data populated: {name}")
        
        # Final stabilization wait
        await page.wait_for_timeout(3000)
        
        return True
        
    except PlaywrightTimeoutError as e:
        logger.warning(f"Timeout waiting for Studio dashboard ({name}): {e}")
        return False

async def wait_for_classic_dashboard(page, name):
    """Wait for Classic dashboard to load completely."""
    try:
        # Wait for dashboard body
        await page.wait_for_selector(".dashboard-body, #dashboard", timeout=30000)
        logger.info(f"Classic dashboard body loaded: {name}")
        
        # Wait for panels to appear
        await page.wait_for_selector(".dashboard-panel, .panel, .dashboard-element", timeout=30000)
        logger.info(f"Classic dashboard panels detected: {name}")
        
        # Wait for searches to complete
        await page.wait_for_function("""
            () => {
                // Look for search status indicators
                const searchStatuses = document.querySelectorAll(
                    '.search-status[data-status="running"]',
                    '.shared-searchbar .search-status',
                    '.dashboard-element[data-status="running"]'
                );
                return searchStatuses.length === 0;
            }
        """, timeout=60000)
        logger.info(f"Classic dashboard searches completed: {name}")
        
        # Wait for visualizations to render
        await page.wait_for_function("""
            () => {
                const vizContainers = document.querySelectorAll(
                    '.viz-container, .chart-container, .table-container, ' +
                    '.single-value-container, .map-container'
                );
                
                let renderedCount = 0;
                vizContainers.forEach(container => {
                    // Check if container has content
                    const hasContent = container.children.length > 0 || 
                                     container.textContent.trim().length > 0;
                    if (hasContent) renderedCount++;
                });
                
                return renderedCount > 0 || vizContainers.length === 0;
            }
        """, timeout=45000)
        logger.info(f"Classic dashboard visualizations rendered: {name}")
        
        # Wait for any remaining loading indicators
        await page.wait_for_function("""
            () => {
                const loadingElements = document.querySelectorAll(
                    '.loading, .spinner, .wait-spinner, [data-status="waiting"]'
                );
                return Array.from(loadingElements).every(el => 
                    el.offsetParent === null || el.style.display === 'none'
                );
            }
        """, timeout=30000)
        logger.info(f"Classic loading indicators cleared: {name}")
        
        # Final stabilization wait
        await page.wait_for_timeout(2000)
        
        return True
        
    except PlaywrightTimeoutError as e:
        logger.warning(f"Timeout waiting for Classic dashboard ({name}): {e}")
        return False

async def capture_dashboard_screenshot(page, name):
    """Capture screenshot of the dashboard."""
    try:
        # Determine dashboard type for optimal screenshot
        is_studio = await detect_dashboard_type(page)
        
        if is_studio:
            # For Studio dashboards, try to get full height
            try:
                # Get the dashboard container height
                dashboard_height = await page.evaluate("""
                    () => {
                        const dashboard = document.querySelector('splunk-dashboard-view');
                        return dashboard ? dashboard.scrollHeight : document.body.scrollHeight;
                    }
                """)
                
                # Set viewport to capture full dashboard
                await page.set_viewport_size({
                    "width": 1280, 
                    "height": min(dashboard_height + 100, 10000)  # Cap at reasonable height
                })
                logger.info(f"Set Studio viewport height to {dashboard_height + 100}")
                
            except Exception as e:
                logger.warning(f"Could not adjust viewport for Studio dashboard: {e}")
        
        # Scroll to top to ensure we capture from the beginning
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(1000)
        
        # Take screenshot
        screenshot_bytes = await page.screenshot(
            full_page=True,
            timeout=30000
        )
        
        # Generate filename with timestamp
        timestamp = datetime.now(Config.EST).strftime('%H%M%S')
        safe_name = re.sub(r'[^A-Za-z0-9]+', '_', name)
        filename = f"{safe_name}_{timestamp}.png"
        
        # Save screenshot with timestamp overlay
        file_path = save_screenshot_to_tmp(screenshot_bytes, filename)
        logger.info(f"Screenshot saved: {file_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error capturing screenshot for '{name}': {e}")
        return False

def format_time_for_url(base_url, start_dt, end_dt, is_studio=None):
    """Format dashboard URL with correct time parameters for Classic or Studio."""
    try:
        # Clean base URL
        base_url = base_url.split('?')[0]
        
        # Determine dashboard type from URL if not specified
        if is_studio is None:
            is_studio = '/app/splunk_dashboard_studio/' in base_url or 'studio' in base_url.lower()
        
        # Handle different time formats
        if isinstance(start_dt, str) and isinstance(end_dt, str):
            # Splunk relative time format (e.g., "-24h", "now")
            earliest = start_dt
            latest = end_dt
        else:
            # DateTime objects - convert to epoch
            if hasattr(start_dt, 'timestamp'):
                earliest = int(start_dt.timestamp())
            else:
                earliest = start_dt
                
            if hasattr(end_dt, 'timestamp'):
                latest = int(end_dt.timestamp())
            else:
                latest = end_dt
        
        # Set parameter prefix based on dashboard type
        if is_studio:
            param_prefix = "form.global_time"
        else:
            param_prefix = "form.time_field"
        
        # Build parameters
        params = {
            f"{param_prefix}.earliest": earliest,
            f"{param_prefix}.latest": latest
        }
        
        # Add parameters to URL
        param_string = '&'.join(f'{k}={v}' for k, v in params.items())
        full_url = f"{base_url}?{param_string}"
        
        return full_url
        
    except Exception as e:
        logger.error(f"Error formatting URL with time parameters: {e}")
        # Return original URL if formatting fails
        return base_url

async def test_dashboard_accessibility(url, username, password):
    """Test if dashboard is accessible with given credentials."""
    async with async_playwright() as playwright:
        browser = None
        try:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()
            
            await page.goto(url, timeout=60000)
            
            # Handle login
            login_success = await handle_splunk_login(page, username, password)
            if not login_success:
                return False, "Login failed"
            
            # Check if dashboard loads
            try:
                # Wait for either Studio or Classic dashboard elements
                await page.wait_for_selector(
                    "splunk-dashboard-view, .dashboard-body, #dashboard",
                    timeout=30000
                )
                return True, "Dashboard accessible"
            except:
                return False, "Dashboard did not load"
                
        except Exception as e:
            return False, f"Error: {e}"
        finally:
            if browser:
                await browser.close()

# Utility function for batch processing
async def process_dashboards_batch(dashboards, start_dt, end_dt, username, password, 
                                 max_concurrent=3, capture_only=False):
    """Process multiple dashboards concurrently with rate limiting."""
    import asyncio
    
    async with async_playwright() as playwright:
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_single_with_semaphore(db):
            async with semaphore:
                return await process_single_dashboard(
                    playwright, db, start_dt, end_dt, username, password, capture_only
                )
        
        # Create tasks for all dashboards
        tasks = [process_single_with_semaphore(db) for db in dashboards]
        
        # Execute all tasks and return results
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return results

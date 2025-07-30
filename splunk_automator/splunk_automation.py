import re
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Page, Browser
from .config import Config
from .screenshot import save_screenshot_to_tmp
from .logging_setup import logger, timing_context

class SplunkDashboardProcessor:
    """Enhanced Splunk dashboard processing with better error handling and performance."""
    
    def __init__(self, max_concurrent: int = None):
        self.max_concurrent = max_concurrent or Config.MAX_CONCURRENT_BROWSERS
        self.browser_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-extensions',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding'
        ]
    
    async def process_single_dashboard(self, playwright, db_data: Dict, start_dt: str, 
                                     end_dt: str, username: str, password: str, 
                                     capture_only: bool = False) -> bool:
        """Process a single dashboard with comprehensive error handling and retries."""
        name = db_data['name']
        
        with timing_context("process_single_dashboard", name):
            logger.info(f"Starting processing for dashboard '{name}' (capture_only={capture_only})")
            
            browser = None
            try:
                # Launch browser with optimized settings
                browser = await self._launch_browser(playwright)
                
                # Create context with dashboard-specific settings
                context = await self._create_browser_context(browser, db_data)
                
                # Create page
                page = await context.new_page()
                
                # Set up page monitoring
                await self._setup_page_monitoring(page, name)
                
                # Navigate to dashboard
                success = await self._navigate_to_dashboard(page, db_data, start_dt, end_dt)
                if not success:
                    return False
                
                # Handle authentication
                login_success = await self._handle_authentication(page, username, password, name)
                if not login_success:
                    return False
                
                # Wait for dashboard to load
                load_success = await self._wait_for_dashboard_load(page, name)
                if not load_success:
                    logger.warning(f"Dashboard may not have loaded completely: {name}")
                
                # Capture screenshot
                screenshot_success = await self._capture_screenshot(page, name)
                
                # Perform analysis if requested
                if not capture_only and screenshot_success:
                    analysis_success = await self._perform_dashboard_analysis(page, db_data)
                    return screenshot_success and analysis_success
                
                return screenshot_success
                
            except Exception as e:
                logger.error(f"Error processing dashboard '{name}': {e}", exc_info=True)
                return False
            finally:
                if browser:
                    try:
                        await browser.close()
                    except Exception as e:
                        logger.warning(f"Error closing browser for {name}: {e}")
    
    async def _launch_browser(self, playwright) -> Browser:
        """Launch browser with optimized settings."""
        return await playwright.chromium.launch(
            headless=True,
            args=self.browser_args
        )
    
    async def _create_browser_context(self, browser: Browser, db_data: Dict):
        """Create browser context with dashboard-specific settings."""
        # Determine optimal viewport size based on dashboard type
        viewport_width = Config.DEFAULT_VIEWPORT_WIDTH
        viewport_height = Config.DEFAULT_VIEWPORT_HEIGHT
        
        # Adjust viewport for known dashboard types
        if 'studio' in db_data.get('url', '').lower():
            viewport_height = 900  # Studio dashboards often need more height
        
        return await browser.new_context(
            viewport={'width': viewport_width, 'height': viewport_height},
            ignore_https_errors=True,
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            }
        )
    
    async def _setup_page_monitoring(self, page: Page, name: str):
        """Set up page monitoring for errors and performance."""
        # Monitor console errors
        async def handle_console_message(msg):
            if msg.type in ['error', 'warning']:
                logger.debug(f"Console {msg.type} in {name}: {msg.text}")
        
        # Monitor page errors
        async def handle_page_error(error):
            logger.warning(f"Page error in {name}: {error}")
        
        # Monitor failed requests
        async def handle_response(response):
            if response.status >= 400:
                logger.debug(f"HTTP {response.status} in {name}: {response.url}")
        
        page.on('console', handle_console_message)
        page.on('pageerror', handle_page_error)
        page.on('response', handle_response)
    
    async def _navigate_to_dashboard(self, page: Page, db_data: Dict, 
                                   start_dt: str, end_dt: str) -> bool:
        """Navigate to dashboard with time parameters."""
        try:
            # Format URL with time parameters
            full_url = self._format_time_for_url(db_data['url'], start_dt, end_dt)
            logger.info(f"Navigating to: {full_url}")
            
            # Navigate with timeout and wait conditions
            response = await page.goto(
                full_url, 
                timeout=Config.BROWSER_TIMEOUT,
                wait_until='networkidle'
            )
            
            if response and response.status >= 400:
                logger.error(f"HTTP {response.status} when accessing dashboard: {db_data['name']}")
                return False
            
            return True
            
        except PlaywrightTimeoutError:
            logger.error(f"Timeout navigating to dashboard: {db_data['name']}")
            return False
        except Exception as e:
            logger.error(f"Error navigating to dashboard {db_data['name']}: {e}")
            return False
    
    async def _handle_authentication(self, page: Page, username: str, 
                                   password: str, dashboard_name: str) -> bool:
        """Handle Splunk authentication with enhanced detection."""
        try:
            # Wait a moment for the page to stabilize
            await page.wait_for_timeout(2000)
            
            # Check for various login form patterns
            login_selectors = [
                'input[name="username"]',
                'input[id="username"]',
                'input[placeholder*="username" i]',
                'input[type="text"][class*="username" i]'
            ]
            
            username_field = None
            for selector in login_selectors:
                try:
                    username_field = await page.wait_for_selector(selector, timeout=5000)
                    if username_field:
                        break
                except:
                    continue
            
            if not username_field:
                # No login form detected, assume already authenticated
                logger.info(f"No login form detected for {dashboard_name}, proceeding")
                return True
            
            logger.info(f"Login form detected for {dashboard_name}, attempting authentication")
            
            # Fill username
            await username_field.fill(username)
            
            # Find password field
            password_selectors = [
                'input[name="password"]',
                'input[id="password"]',
                'input[type="password"]'
            ]
            
            password_field = None
            for selector in password_selectors:
                try:
                    password_field = page.locator(selector)
                    if await password_field.count() > 0:
                        break
                except:
                    continue
            
            if not password_field:
                logger.error(f"Password field not found for {dashboard_name}")
                return False
            
            await password_field.fill(password)
            
            # Submit form
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Sign In")',
                'button:has-text("Log In")',
                'button:has-text("Login")'
            ]
            
            submit_button = None
            for selector in submit_selectors:
                try:
                    submit_button = page.locator(selector)
                    if await submit_button.count() > 0:
                        break
                except:
                    continue
            
            if submit_button:
                await submit_button.click()
            else:
                # Try submitting with Enter key
                await password_field.press('Enter')
            
            # Wait for login to complete
            try:
                # Wait for URL to change away from login page
                await page.wait_for_function(
                    '''() => {
                        const url = window.location.href.toLowerCase();
                        return !url.includes('login') && !url.includes('account/login');
                    }''',
                    timeout=15000
                )
                
                # Additional check for login success indicators
                await page.wait_for_timeout(2000)
                
                # Check if we're still on a login page
                current_url = page.url.lower()
                if 'login' in current_url:
                    logger.error(f"Login failed for {dashboard_name} - still on login page")
                    return False
                
                logger.info(f"Authentication successful for {dashboard_name}")
                return True
                
            except PlaywrightTimeoutError:
                logger.error(f"Login timeout for {dashboard_name} - credentials may be incorrect")
                return False
                
        except Exception as e:
            logger.error(f"Authentication error for {dashboard_name}: {e}")
            return False
    
    async def _wait_for_dashboard_load(self, page: Page, name: str) -> bool:
        """Wait for dashboard to fully load with type detection."""
        try:
            logger.info(f"Waiting for dashboard to load: {name}")
            
            # Detect dashboard type
            is_studio = await self._detect_dashboard_type(page)
            logger.info(f"Dashboard type detected - Studio: {is_studio} for {name}")
            
            if is_studio:
                return await self._wait_for_studio_dashboard(page, name)
            else:
                return await self._wait_for_classic_dashboard(page, name)
                
        except Exception as e:
            logger.error(f"Error waiting for dashboard to load ({name}): {e}")
            return False
    
    async def _detect_dashboard_type(self, page: Page) -> bool:
        """Detect if dashboard is Studio or Classic with multiple methods."""
        try:
            # Method 1: Check for Studio-specific elements
            studio_selectors = [
                'splunk-dashboard-view',
                'dashboard-view',
                '[data-test="dashboard-view"]'
            ]
            
            for selector in studio_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    return True
                except:
                    continue
            
            # Method 2: Check URL patterns
            url = page.url.lower()
            if any(pattern in url for pattern in ['studio', 'dashboard_studio']):
                return True
            
            # Method 3: Check for Classic dashboard elements
            classic_selectors = [
                '.dashboard-body',
                '#dashboard',
                '.dashboard-element',
                '.dashboard-panel'
            ]
            
            for selector in classic_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    return False
                except:
                    continue
            
            # Default to Classic if can't determine
            return False
            
        except Exception as e:
            logger.warning(f"Error detecting dashboard type: {e}")
            return False
    
    async def _wait_for_studio_dashboard(self, page: Page, name: str) -> bool:
        """Wait for Studio dashboard to load completely."""
        try:
            with timing_context("wait_for_studio_dashboard", name):
                # Wait for main dashboard container
                await page.wait_for_selector("splunk-dashboard-view", timeout=Config.STUDIO_LOAD_TIMEOUT)
                logger.debug(f"Studio dashboard container loaded: {name}")
                
                # Wait for visualizations to appear
                await page.wait_for_function("""
                    () => {
                        const vizElements = document.querySelectorAll(
                            'splunk-viz, splunk-single-value, splunk-table, splunk-choropleth-map, ' +
                            'splunk-cluster-map, splunk-bubble-chart, splunk-sankey-diagram, ' +
                            'splunk-timeline, splunk-scatter-chart'
                        );
                        return vizElements.length > 0;
                    }
                """, timeout=30000)
                logger.debug(f"Studio visualizations detected: {name}")
                
                # Wait for loading states to complete
                await page.wait_for_function("""
                    () => {
                        const loadingSelectors = [
                            '[data-test="loading"]',
                            '.loading',
                            '.spinner',
                            '.wait-spinner',
                            '[aria-label*="loading" i]',
                            '.viz-loading',
                            '[data-test="viz-loading"]'
                        ];
                        
                        for (const selector of loadingSelectors) {
                            const elements = document.querySelectorAll(selector);
                            for (const el of elements) {
                                if (el.offsetParent !== null && 
                                    window.getComputedStyle(el).display !== 'none') {
                                    return false;
                                }
                            }
                        }
                        return true;
                    }
                """, timeout=60000)
                logger.debug(f"Studio loading indicators cleared: {name}")
                
                # Wait for data to populate
                await page.wait_for_function("""
                    () => {
                        const vizElements = document.querySelectorAll('splunk-viz, splunk-single-value, splunk-table');
                        let hasContent = false;
                        
                        vizElements.forEach(el => {
                            const textContent = el.textContent || '';
                            const hasNumbers = /\d+/.test(textContent);
                            const hasText = textContent.trim().length > 10;
                            const hasNoDataMessage = /no\s+data|no\s+results/i.test(textContent);
                            
                            if ((hasNumbers || hasText) && !hasNoDataMessage) {
                                hasContent = true;
                            }
                        });
                        
                        return hasContent || vizElements.length === 0;
                    }
                """, timeout=45000)
                logger.debug(f"Studio dashboard data populated: {name}")
                
                # Final stabilization wait
                await page.wait_for_timeout(Config.STABILIZATION_WAIT)
                
                return True
                
        except PlaywrightTimeoutError as e:
            logger.warning(f"Timeout waiting for Studio dashboard ({name}): {e}")
            return False
        except Exception as e:
            logger.error(f"Error waiting for Studio dashboard ({name}): {e}")
            return False
    
    async def _wait_for_classic_dashboard(self, page: Page, name: str) -> bool:
        """Wait for Classic dashboard to load completely."""
        try:
            with timing_context("wait_for_classic_dashboard", name):
                # Wait for dashboard body
                await page.wait_for_selector(".dashboard-body, #dashboard", timeout=30000)
                logger.debug(f"Classic dashboard body loaded: {name}")
                
                # Wait for panels to appear
                await page.wait_for_selector(".dashboard-panel, .panel, .dashboard-element", timeout=30000)
                logger.debug(f"Classic dashboard panels detected: {name}")
                
                # Wait for searches to complete
                await page.wait_for_function("""
                    () => {
                        const runningSearches = document.querySelectorAll(
                            '.search-status[data-status="running"]',
                            '.shared-searchbar .search-status[data-status="running"]',
                            '.dashboard-element[data-status="running"]'
                        );
                        return runningSearches.length === 0;
                    }
                """, timeout=Config.CLASSIC_LOAD_TIMEOUT)
                logger.debug(f"Classic dashboard searches completed: {name}")
                
                # Wait for visualizations to render
                await page.wait_for_function("""
                    () => {
                        const vizContainers = document.querySelectorAll(
                            '.viz-container, .chart-container, .table-container, ' +
                            '.single-value-container, .map-container, .dashboard-viz'
                        );
                        
                        let renderedCount = 0;
                        vizContainers.forEach(container => {
                            const hasContent = container.children.length > 0 || 
                                             container.textContent.trim().length > 0;
                            if (hasContent) renderedCount++;
                        });
                        
                        return renderedCount > 0 || vizContainers.length === 0;
                    }
                """, timeout=45000)
                logger.debug(f"Classic dashboard visualizations rendered: {name}")
                
                # Wait for loading indicators to disappear
                await page.wait_for_function("""
                    () => {
                        const loadingElements = document.querySelectorAll(
                            '.loading, .spinner, .wait-spinner, [data-status="waiting"]'
                        );
                        return Array.from(loadingElements).every(el => 
                            el.offsetParent === null || 
                            el.style.display === 'none' ||
                            window.getComputedStyle(el).display === 'none'
                        );
                    }
                """, timeout=30000)
                logger.debug(f"Classic loading indicators cleared: {name}")
                
                # Final stabilization wait
                await page.wait_for_timeout(2000)
                
                return True
                
        except PlaywrightTimeoutError as e:
            logger.warning(f"Timeout waiting for Classic dashboard ({name}): {e}")
            return False
        except Exception as e:
            logger.error(f"Error waiting for Classic dashboard ({name}): {e}")
            return False
    
    async def _capture_screenshot(self, page: Page, name: str) -> bool:
        """Capture dashboard screenshot with optimization."""
        try:
            with timing_context("capture_screenshot", name):
                # Determine dashboard type for optimal screenshot
                is_studio = await self._detect_dashboard_type(page)
                
                if is_studio:
                    # For Studio dashboards, try to get full height
                    try:
                        dashboard_height = await page.evaluate("""
                            () => {
                                const dashboard = document.querySelector('splunk-dashboard-view');
                                if (dashboard) {
                                    return Math.min(dashboard.scrollHeight, 10000);
                                }
                                return Math.min(document.body.scrollHeight, 10000);
                            }
                        """)
                        
                        # Set viewport to capture full dashboard
                        await page.set_viewport_size({
                            "width": Config.DEFAULT_VIEWPORT_WIDTH,
                            "height": min(dashboard_height + 100, Config.MAX_SCREENSHOT_HEIGHT)
                        })
                        logger.debug(f"Set Studio viewport height to {dashboard_height + 100} for {name}")
                        
                    except Exception as e:
                        logger.warning(f"Could not adjust viewport for Studio dashboard {name}: {e}")
                
                # Scroll to top to ensure we capture from the beginning
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(1000)
                
                # Hide scrollbars for cleaner screenshots
                await page.add_style_tag(content="""
                    ::-webkit-scrollbar { display: none; }
                    html { scrollbar-width: none; }
                """)
                
                # Take screenshot with error handling
                screenshot_bytes = await page.screenshot(
                    full_page=True,
                    timeout=Config.SCREENSHOT_TIMEOUT,
                    type='png',
                    quality=85 if page.url.startswith('https') else 100  # Slight compression for HTTPS
                )
                
                # Generate filename with timestamp
                timestamp = datetime.now(Config.EST).strftime('%H%M%S')
                safe_name = self._sanitize_filename(name)
                filename = f"{safe_name}_{timestamp}.png"
                
                # Save screenshot with timestamp overlay
                file_path = save_screenshot_to_tmp(screenshot_bytes, filename)
                logger.info(f"Screenshot saved: {file_path}")
                
                return True
                
        except PlaywrightTimeoutError:
            logger.error(f"Timeout capturing screenshot for '{name}'")
            return False
        except Exception as e:
            logger.error(f"Error capturing screenshot for '{name}': {e}")
            return False
    
    async def _perform_dashboard_analysis(self, page: Page, db_data: Dict) -> bool:
        """Perform additional dashboard analysis if needed."""
        try:
            name = db_data['name']
            with timing_context("dashboard_analysis", name):
                # Extract dashboard metadata
                metadata = await self._extract_dashboard_metadata(page)
                
                # Check for errors or warnings in the dashboard
                issues = await self._check_dashboard_issues(page)
                
                # Log analysis results
                if metadata:
                    logger.info(f"Dashboard analysis for {name}: {len(metadata.get('visualizations', []))} visualizations found")
                
                if issues:
                    logger.warning(f"Dashboard issues found for {name}: {len(issues)} issues")
                    for issue in issues[:5]:  # Log first 5 issues
                        logger.warning(f"  - {issue}")
                
                return True
                
        except Exception as e:
            logger.error(f"Error performing dashboard analysis for {db_data['name']}: {e}")
            return False
    
    async def _extract_dashboard_metadata(self, page: Page) -> Dict[str, Any]:
        """Extract metadata from the dashboard."""
        try:
            metadata = await page.evaluate("""
                () => {
                    const metadata = {
                        title: document.title || '',
                        url: window.location.href,
                        visualizations: [],
                        panels: [],
                        searches: []
                    };
                    
                    // Extract Studio visualizations
                    const studioViz = document.querySelectorAll('splunk-viz, splunk-single-value, splunk-table');
                    studioViz.forEach(viz => {
                        metadata.visualizations.push({
                            type: viz.tagName.toLowerCase(),
                            id: viz.id || 'unnamed',
                            hasData: (viz.textContent || '').trim().length > 0
                        });
                    });
                    
                    // Extract Classic panels
                    const classicPanels = document.querySelectorAll('.dashboard-panel, .dashboard-element');
                    classicPanels.forEach(panel => {
                        metadata.panels.push({
                            id: panel.id || 'unnamed',
                            title: (panel.querySelector('.panel-title') || {}).textContent || '',
                            type: panel.className || ''
                        });
                    });
                    
                    return metadata;
                }
            """)
            
            return metadata
            
        except Exception as e:
            logger.warning(f"Error extracting dashboard metadata: {e}")
            return {}
    
    async def _check_dashboard_issues(self, page: Page) -> List[str]:
        """Check for common dashboard issues."""
        try:
            issues = await page.evaluate("""
                () => {
                    const issues = [];
                    
                    // Check for error messages
                    const errorElements = document.querySelectorAll(
                        '[class*="error"], [data-test*="error"], .alert-error, .error-message'
                    );
                    errorElements.forEach(el => {
                        const text = el.textContent.trim();
                        if (text && text.length > 0 && text.length < 200) {
                            issues.push('Error: ' + text);
                        }
                    });
                    
                    // Check for "No data" messages
                    const noDataElements = document.querySelectorAll('*');
                    Array.from(noDataElements).forEach(el => {
                        const text = el.textContent || '';
                        if (/no\s+data|no\s+results|no\s+events/i.test(text) && 
                            text.length < 100 && 
                            el.children.length === 0) {
                            issues.push('No data: ' + text.trim());
                        }
                    });
                    
                    // Check for loading indicators that are stuck
                    const loadingElements = document.querySelectorAll('.loading, .spinner, [data-test="loading"]');
                    loadingElements.forEach(el => {
                        if (el.offsetParent !== null) {
                            issues.push('Stuck loading indicator detected');
                        }
                    });
                    
                    return [...new Set(issues)]; // Remove duplicates
                }
            """)
            
            return issues
            
        except Exception as e:
            logger.warning(f"Error checking dashboard issues: {e}")
            return []
    
    def _format_time_for_url(self, base_url: str, start_dt: str, end_dt: str) -> str:
        """Format dashboard URL with correct time parameters."""
        try:
            # Clean base URL
            base_url = base_url.split('?')[0]
            
            # Determine dashboard type from URL
            is_studio = any(pattern in base_url.lower() for pattern in ['/app/splunk_dashboard_studio/', 'studio'])
            
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
            return base_url
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe file system usage."""
        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)
        filename = filename.strip(' .')
        
        if not filename:
            filename = "unnamed_dashboard"
        
        # Limit length
        if len(filename) > 100:
            filename = filename[:100]
        
        return filename

# Batch processing functions
async def process_dashboards_batch(dashboards: List[Dict], start_dt: str, end_dt: str, 
                                 username: str, password: str, max_concurrent: int = None,
                                 capture_only: bool = False) -> List[bool]:
    """Process multiple dashboards concurrently with enhanced error handling."""
    max_concurrent = max_concurrent or Config.MAX_CONCURRENT_BROWSERS
    processor = SplunkDashboardProcessor(max_concurrent)
    
    async with async_playwright() as playwright:
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_single_with_semaphore(db):
            async with semaphore:
                return await processor.process_single_dashboard(
                    playwright, db, start_dt, end_dt, username, password, capture_only
                )
        
        # Create tasks for all dashboards
        tasks = [process_single_with_semaphore(db) for db in dashboards]
        
        # Execute all tasks and return results
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to False
        return [result if isinstance(result, bool) else False for result in results]

async def test_dashboard_accessibility(url: str, username: str, password: str) -> Tuple[bool, str]:
    """Test if dashboard is accessible with given credentials."""
    processor = SplunkDashboardProcessor(1)
    
    async with async_playwright() as playwright:
        browser = None
        try:
            browser = await processor._launch_browser(playwright)
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()
            
            # Navigate to dashboard
            response = await page.goto(url, timeout=60000)
            
            if response and response.status >= 400:
                return False, f"HTTP {response.status} error"
            
            # Handle login
            login_success = await processor._handle_authentication(page, username, password, "test")
            if not login_success:
                return False, "Authentication failed"
            
            # Check if dashboard loads
            try:
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

# Backward compatibility functions
async def process_single_dashboard(playwright, db_data, start_dt, end_dt, username, password, capture_only=False):
    """Backward compatible function."""
    processor = SplunkDashboardProcessor()
    return await processor.process_single_dashboard(
        playwright, db_data, start_dt, end_dt, username, password, capture_only
    )

async def handle_splunk_login(page, username, password):
    """Backward compatible login function."""
    processor = SplunkDashboardProcessor()
    return await processor._handle_authentication(page, username, password, "dashboard")

async def wait_for_splunk_dashboard_to_load(page, name):
    """Backward compatible dashboard load function."""
    processor = SplunkDashboardProcessor()
    return await processor._wait_for_dashboard_load(page, name)

async def capture_dashboard_screenshot(page, name):
    """Backward compatible screenshot function."""
    processor = SplunkDashboardProcessor()
    return await processor._capture_screenshot(page, name)

def format_time_for_url(base_url, start_dt, end_dt, is_studio=None):
    """Backward compatible URL formatting function."""
    processor = SplunkDashboardProcessor()
    return processor._format_time_for_url(base_url, start_dt, end_dt)

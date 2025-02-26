import os
import logging
from typing import Optional, Tuple
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait

# Setup logging
logger = logging.getLogger(__name__)

def capture_website_screenshot(url: str, session_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Capture a screenshot of a website's viewport using Selenium with Chrome headless.
    Returns a tuple of (screenshot_path, error_message).
    """
    # Directory to save screenshots
    screenshots_dir = os.path.join('static', 'screenshots')
    os.makedirs(screenshots_dir, exist_ok=True)
    screenshot_path = os.path.join(screenshots_dir, f'{session_id}.png')

    # Chrome options for headless mode
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # Run in headless mode
    chrome_options.add_argument('--no-sandbox')  # Required for container environments
    chrome_options.add_argument('--disable-dev-shm-usage')  # Optimize for low resources
    chrome_options.add_argument('--window-size=1280,800')  # Viewport size

    driver = None
    try:
        # Use WebDriver Manager to handle ChromeDriver automatically
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Set page load timeout (30 seconds)
        driver.set_page_load_timeout(30)

        # Navigate to the URL
        driver.get(url)

        # Wait for the page to fully load
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )

        # Take screenshot and save it
        driver.save_screenshot(screenshot_path)

        logger.info(f"Screenshot captured successfully for {url}")
        return f'/static/screenshots/{session_id}.png', None

    except Exception as e:
        error_msg = f"Screenshot capture failed: {str(e)}"
        logger.error(error_msg)
        return None, error_msg

    finally:
        if driver:
            driver.quit()

# Example usage for testing
if __name__ == "__main__":
    test_url = "https://www.example.com"
    session_id = "example_session"
    screenshot, error = capture_website_screenshot(test_url, session_id)
    if screenshot:
        print(f"Screenshot saved: {screenshot}")
    else:
        print(f"Error: {error}")

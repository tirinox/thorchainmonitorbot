import logging

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright, Page


class Renderer:
    """
    Renderer class to manage Playwright browser instance and render HTML to PNG.
    Supports dynamic viewport sizes per rendering request.
    """

    def __init__(self, templates_dir: str,
                 device_scale_factor: int = 2):
        self.templates_dir = templates_dir
        self.default_viewport = {'width': 1280, 'height': 720}
        self.device_scale_factor = device_scale_factor
        self.playwright = None
        self.browser = None
        self.browser_context = None
        self.jinja_env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )
        logging.info(f"Renderer initialized with templates directory: {self.templates_dir}")

    async def start(self):
        """
        Initialize Playwright and launch the browser.
        """
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.browser_context = await self.browser.new_context(
            viewport=self.default_viewport,
            device_scale_factor=self.device_scale_factor
        )
        logging.info(f"Browser launched and context created with default viewport: {self.default_viewport}")

    async def stop(self):
        """
        Close the browser and Playwright.
        """
        if self.browser_context:
            await self.browser_context.close()
            logging.info("Browser context closed.")
        if self.browser:
            await self.browser.close()
            logging.info("Browser closed.")
        if self.playwright:
            await self.playwright.stop()
            logging.info("Playwright stopped.")

    def render_template(self, template_name: str, parameters: dict) -> str:
        """
        Render a Jinja2 template with the given parameters.
        """
        try:
            template = self.jinja_env.get_template(template_name)
            rendered_html = template.render(parameters)
            logging.info(f"Template {template_name} rendered with parameters: {parameters}")
            return rendered_html
        except Exception as e:
            logging.error(f"Error rendering template '{template_name}': {e}")
            raise e

    async def render_html_to_png(self, html_content: str, width: int = 0, height: int = 0) -> bytes:
        """
        Render HTML content to PNG using Playwright with dynamic viewport sizes.
        If width and height are not provided, use the default viewport from the context.
        """
        try:
            # Create a new page
            page: Page = await self.browser_context.new_page()

            # If width and height are specified, set the viewport for this page
            if width and height:
                await page.set_viewport_size({'width': int(width), 'height': int(height)})
                logging.info(f"Set viewport size to {width=}, {height=}")
            else:
                await page.set_viewport_size(self.default_viewport)

            # Set the HTML content
            await page.set_content(html_content, wait_until='networkidle')

            # Take a screenshot
            png_bytes = await page.screenshot(full_page=True)

            # Close the page
            await page.close()

            logging.info(f"HTML content rendered to PNG successfully with viewport size: {width=}, {height=}")
            return png_bytes
        except Exception as e:
            logging.error(f"Error rendering HTML to PNG: {e}")
            raise e

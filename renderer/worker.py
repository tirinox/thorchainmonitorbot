import asyncio
import json
import os
import time

import redis.asyncio as redis
from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright

from const import RESPONSE_STREAM, REQUEST_STREAM

# Redis Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6382))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '12345678')
REDIS_DB_INDEX = int(os.getenv('REDIS_DB_INDEX', 0))

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(['html', 'xml'])
)


async def render_template(template_name, parameters):
    try:
        template = env.get_template(template_name)
        rendered_html = template.render(parameters)
        return rendered_html
    except Exception as e:
        print(f"Error rendering template '{template_name}': {e}")
        raise


async def render_html_to_png(browser, html_content, w=1280, h=720):
    start = time.monotonic()
    # async with async_playwright() as p:
    #     browser = await p.chromium.launch()
    page = await browser.new_page(
        viewport={'width': w, 'height': h},
        device_scale_factor=2
    )
    await page.set_content(html_content)
    png_bytes = await page.screenshot()
    print(f"Rendered PNG image in {time.monotonic() - start:.2f} seconds.")
    return png_bytes


async def process_message(browser, message, redis_client):
    message_id = None
    try:
        message_id, message_data = message

        data = json.loads(message_data[b'data'])
        template_name = data.get('template_name')
        parameters = data.get('parameters', {})
        correlation_id = data.get('correlation_id', '')
        reply_to = data.get('reply_to', RESPONSE_STREAM)

        width = parameters.get('width', 1280)
        height = parameters.get('height', 720)

        if not template_name:
            raise ValueError("No template name provided.")

        print(f"Received template '{template_name}' with correlation_id: {correlation_id} ({width} x {height})")

        # Render HTML using Jinja2
        rendered_html = await render_template(template_name, parameters)

        # Render HTML to PNG
        png_bytes = await render_html_to_png(browser, rendered_html, width, height)

        # Prepare response
        response = {
            'correlation_id': correlation_id,
            'png_data': png_bytes.hex()  # Send as hex string
        }

        # Send response to the response stream
        await redis_client.xadd(reply_to, {'data': json.dumps(response)})

        print(f"PNG image for correlation_id {correlation_id} sent back to stream '{reply_to}'.")

    except Exception as e:
        print(f"Error processing message ID {message_id}: {e}")


async def worker(browser):
    redis_host = REDIS_HOST
    redis_port = REDIS_PORT
    redis_password = REDIS_PASSWORD
    redis_db = REDIS_DB_INDEX

    redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=False,
                               password=redis_password, db=redis_db)

    print("Worker started. Waiting for messages...")

    # Start reading from the stream
    # Use a consumer group for better scalability and message acknowledgment
    group_name = 'html_renderer_group'
    consumer_name = 'consumer_1'

    try:
        await redis_client.xgroup_create(name=REQUEST_STREAM, groupname=group_name, id='0', mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            # Group already exists
            pass
        else:
            raise e

    while True:
        try:
            # Read messages from the stream
            messages = await redis_client.xreadgroup(
                group_name,
                consumer_name,
                {REQUEST_STREAM: '>'},
                count=1,
                block=5000  # milliseconds
            )

            if messages:
                for stream, msgs in messages:
                    for msg in msgs:
                        await process_message(browser, msg, redis_client)
                        # Acknowledge the message
                        await redis_client.xack(REQUEST_STREAM, group_name, msg[0])
        except Exception as e:
            print(f"Error in worker loop: {e}")
            await asyncio.sleep(1)  # Prevent tight loop on error


async def main():
    # Initialize Playwright to ensure it's installed
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            await worker(browser)
        finally:
            print("Closing browser...")
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

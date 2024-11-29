import logging
import os
import json
import asyncio
import redis.asyncio as redis
from playwright.async_api import async_playwright

from const import RESPONSE_STREAM, REQUEST_STREAM

# Redis Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6382))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '12345678')
REDIS_DB_INDEX = int(os.getenv('REDIS_DB_INDEX', 0))


async def render_html_to_png(html_content):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html_content)
        png_bytes = await page.screenshot()
        await browser.close()
        return png_bytes


async def process_message(message, redis_client):
    try:
        message_id, message_data = message
        data = json.loads(message_data[b'data'])
        html = data.get('html')
        correlation_id = data.get('correlation_id', '')
        reply_to = data.get('reply_to', RESPONSE_STREAM)

        if not html:
            raise ValueError("No HTML content provided.")

        print(f"Received HTML content. Rendering to PNG... (Correlation ID: {correlation_id})")

        png_bytes = await render_html_to_png(html)

        response = {
            'correlation_id': correlation_id,
            'png_data': png_bytes.hex()  # Send as hex string
        }

        data = {'data': json.dumps(response)}
        data_size = len(data)
        await redis_client.xadd(reply_to, data)

        print(f"PNG image sent back to stream '{reply_to}' (Correlation ID: {correlation_id}), size: {data_size} bytes")

        # Acknowledge the message by acknowledging the consumer's last ID
        # Not necessary with Redis Streams as they are log-based
    except Exception as e:
        logging.exception(f"Error processing message: {e}")


async def worker():
    redis_host = REDIS_HOST
    redis_port = REDIS_PORT
    redis_password = REDIS_PASSWORD
    redis_db = REDIS_DB_INDEX

    redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=False,
                               password=redis_password, db=redis_db)

    # Initialize Playwright to ensure it's installed
    async with async_playwright() as p:
        pass

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
                        await process_message(msg, redis_client)
                        # Acknowledge the message
                        await redis_client.xack(REQUEST_STREAM, group_name, msg[0])
        except Exception as e:
            print(f"Error in worker loop: {e}")
            await asyncio.sleep(1)  # Prevent tight loop on error


if __name__ == "__main__":
    asyncio.run(worker())

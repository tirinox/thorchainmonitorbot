import os

import redis.asyncio as redis
import json
import uuid
import asyncio

from renderer.const import RESPONSE_STREAM, REQUEST_STREAM
from tools.lib.lp_common import LpAppFramework

# Redis Configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6382
REDIS_PASSWORD = '12345678'
REDIS_DB_INDEX = 0

OUT_FILE = '../temp/renderer_output.png'


async def send_html_request(html_content):
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT,
                               password=REDIS_PASSWORD, db=REDIS_DB_INDEX,
                               decode_responses=True)

    correlation_id = str(uuid.uuid4())

    message = {
        'html': html_content,
        'correlation_id': correlation_id,
        'reply_to': RESPONSE_STREAM
    }

    # Add message to the request stream
    await redis_client.xadd(REQUEST_STREAM, {'data': json.dumps(message)})

    print(f"Sent HTML request with correlation_id: {correlation_id}")

    # Listen for the response
    while True:
        try:
            messages = await redis_client.xread(
                streams={RESPONSE_STREAM: '0'},
                count=10,
                block=5000  # milliseconds
            )

            if messages:
                for stream, msgs in messages:
                    for msg_id, msg_data in msgs:
                        data = json.loads(msg_data['data'])
                        if data.get('correlation_id') == correlation_id:
                            png_data_hex = data.get('png_data')
                            png_bytes = bytes.fromhex(png_data_hex)
                            with open(OUT_FILE, 'wb') as f:
                                f.write(png_bytes)
                                os.system(f'open "{OUT_FILE}"')
                            print("Received PNG image and saved as output.png")
                            input("Press Enter to continue...")

        except Exception as e:
            print(f"Error receiving response: {e}")
            await asyncio.sleep(1)


if __name__ == "__main__":
    sample_html = """
    <html>
        <head>
            <title>Test Render</title>
        </head>
        <body>
            <h1>Hello, World!</h1>
            <p>This is a test HTML to PNG rendering.</p>
        </body>
    </html>
    """
    LpAppFramework.solve_working_dir_mess()
    asyncio.run(send_html_request(sample_html))

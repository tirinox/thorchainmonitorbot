import asyncio
import json
import logging
import os
from pprint import pprint

from lib.texts import sep


def read_var_file():
    file_name = '../temp/var.json'
    if os.path.exists(file_name):
        try:
            with open(file_name, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f'Failed to read var file: {e}')
            return {}
    else:
        # write empty file
        with open(file_name, 'w') as f:
            logging.info(f'Created empty var file: {file_name}')
            json.dump({}, f)

        return {}


async def var_file_loop(f_on_change=None, f_every_tick=None, sleep_time=3.0):
    prev_var = None
    while True:
        var_file = read_var_file()

        try:
            if f_every_tick:
                await f_every_tick(var_file)
        except Exception as e:
            logging.error(f'Error in var file loop {f_every_tick = }: {e}')

        if var_file != prev_var:
            sep('New var values detected:')
            pprint(var_file)

            try:
                if f_on_change:
                    await f_on_change(prev_var, var_file)
            except Exception as e:
                logging.error(f'Error in var file loop {f_on_change = }: {e}')

            prev_var = var_file

        await asyncio.sleep(sleep_time)

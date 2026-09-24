"""
Alert previews: what a scheduled job would post, stored for the dashboard to show.

The bot builds the messages in "preview" mode (see lib.run_context and Broadcaster.capture) and saves them here
under the run id; the dashboard reads them back. Everything expires after an hour.
"""
import base64
import json
import time
from typing import Optional

from lib.db import DB
from lib.draw_utils import img_to_bio
from notify.broadcast import CapturedMessage
from notify.channel import MessageType


class AlertPreviewStore:
    PREFIX = 'Dashboard:Preview'
    TTL_SEC = 60 * 60

    def __init__(self, db: DB):
        self.db = db

    def _key(self, run_id: str) -> str:
        return f'{self.PREFIX}:{run_id}'

    def _image_key(self, run_id: str, index: int) -> str:
        return f'{self.PREFIX}:{run_id}:img:{index}'

    @staticmethod
    def _image_bytes(message) -> bytes:
        bio = img_to_bio(message.photo, message.photo_file_name)
        return bio.getvalue()

    async def save(self, run_id: str, captured: list[CapturedMessage]) -> dict:
        if not run_id:
            raise ValueError('A preview needs a run id')

        # channels with the same language share one generated message (and one image); store each image once
        image_index_by_photo = {}
        messages = []
        for item in captured:
            msg = item.message
            image_index = None
            if msg.photo is not None:
                image_index = image_index_by_photo.get(id(msg.photo))
                if image_index is None:
                    image_index = len(image_index_by_photo)
                    image_index_by_photo[id(msg.photo)] = image_index
                    encoded = base64.b64encode(self._image_bytes(msg)).decode('ascii')
                    await self.db.redis.set(self._image_key(run_id, image_index), encoded, ex=self.TTL_SEC)
            messages.append({
                'channel': {
                    'type': item.channel.type,
                    'channel': str(item.channel.channel_id),
                    'lang': str(item.channel.lang),
                    'selector': item.channel.short_coded,
                },
                'text': msg.text or '',
                'message_type': msg.message_type.value if isinstance(msg.message_type, MessageType) else str(
                    msg.message_type),
                'msg_type': msg.msg_type,
                'image': image_index,
                'blocked_by_flag': item.blocked_by_flag,
            })

        preview = {'run_id': run_id, 'created_ts': time.time(), 'messages': messages}
        await self.db.redis.set(self._key(run_id), json.dumps(preview), ex=self.TTL_SEC)
        return preview

    async def load(self, run_id: str) -> Optional[dict]:
        raw = await self.db.redis.get(self._key(run_id))
        return json.loads(raw) if raw else None

    async def load_image(self, run_id: str, index: int) -> Optional[bytes]:
        raw = await self.db.redis.get(self._image_key(run_id, index))
        return base64.b64decode(raw) if raw else None

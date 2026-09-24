from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from dashboard.context import DashboardContext
from dashboard.routes.deps import get_ctx
from notify.alert_preview import AlertPreviewStore

router = APIRouter(prefix='/previews', tags=['previews'])


def _image_media_type(data: bytes) -> str:
    if data.startswith(b'\x89PNG'):
        return 'image/png'
    if data.startswith(b'\xff\xd8'):
        return 'image/jpeg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return 'application/octet-stream'


@router.get('/{run_id}')
async def get_preview(run_id: str, ctx: DashboardContext = Depends(get_ctx)):
    """Messages built by a "preview" run: per channel text, image index and whether a flag would block it."""
    preview = await AlertPreviewStore(ctx.deps.db).load(run_id)
    if not preview:
        raise HTTPException(404, 'No such preview (they expire after an hour)')
    return preview


@router.get('/{run_id}/images/{index}')
async def get_preview_image(run_id: str, index: int, ctx: DashboardContext = Depends(get_ctx)):
    data = await AlertPreviewStore(ctx.deps.db).load_image(run_id, index)
    if data is None:
        raise HTTPException(404, 'No such image (previews expire after an hour)')
    return Response(data, media_type=_image_media_type(data), headers={'Cache-Control': 'private, max-age=3600'})

import asyncio
from .get_volume_outlier import get_volume_outlier

async def get_signals():
    msg = await get_volume_outlier()
    return msg
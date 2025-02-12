
import asyncio
from .get_volume_outlier import get_volume_outlier

def get_signals():
    msg = get_volume_outlier()
    return msg
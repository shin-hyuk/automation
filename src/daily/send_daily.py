import asyncio
import os
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from dotenv import load_dotenv
from datetime import datetime
from utils import send_message
from daily import get_daily1, get_daily2

# Load environment variables
load_dotenv()
TRADE_CHAT_IDS = os.getenv("TRADE_CHAT_IDS", "").split(",")

async def send_daily():
    print("Starting daily workflows...")

    try:
        # # Send first daily message
        # msg = get_daily1()
        # await send_message(msg, chat_ids=TRADE_CHAT_IDS)
        # print("Daily message 1 sent successfully")

        # Send second daily message
        msg = get_daily2()
        await send_message(msg, chat_ids=TRADE_CHAT_IDS)
        print("Daily message 2 sent successfully")

        print("All daily workflows completed.")
    except Exception as e:
        error_msg = f"Error in daily workflow: {str(e)}"
        print(error_msg)

if __name__ == "__main__":
    asyncio.run(send_daily())

import asyncio
import os
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from dotenv import load_dotenv
from utils import send_message
from signals import get_signals

# Load environment variables
load_dotenv()
TRADE_CHAT_IDS = os.getenv("TRADE_CHAT_IDS", "").split(",")

async def send_signals():
    print("Starting signals workflow...")

    try:
        # Get and send signals
        signal = await get_signals()  # Add await here since get_signals is now async
        if signal:
            await send_message(signal, chat_ids=TRADE_CHAT_IDS)
            print("Signals sent successfully")
        else:
            print("No signals to send")

        print("Signals workflow completed.")
    except Exception as e:
        error_msg = f"Error in signals workflow: {str(e)}"
        print(error_msg)

if __name__ == "__main__":
    asyncio.run(send_signals())

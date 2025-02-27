import asyncio
import os
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from dotenv import load_dotenv
from utils import send_message
from signals import get_alerts

# Load environment variables
load_dotenv()
TRADE_CHAT_IDS = os.getenv("TRADE_CHAT_IDS", "").split(",")

async def send_signals():
    try:
        print("\nAnalyzing market signals...")
        signal = get_alerts()
        if signal:
            print("Signals found, sending to channels...")
            await send_message(signal, chat_ids=TRADE_CHAT_IDS)
            print("Signals sent successfully")
        else:
            print("No trading signals detected")
            
    except Exception as e:
        print(f"Failed to process trading signals: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(send_signals())

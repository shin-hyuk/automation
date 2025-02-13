import btc
import crypto

def get_daily2():
    print("\nGenerating daily report (part 2)...")
    try:
        msg = btc.get_chain()
        msg += "\n" + btc.get_world_liberty()
        print("Daily report (part 2) completed\n")
        return msg
        
    except Exception as e:
        print(f"Failed to generate daily report: {str(e)}\n")
        raise
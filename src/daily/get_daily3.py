import btc

def get_daily3():
    print("\nGenerating daily report (part 3)...")
    try:
        msg = btc.get_entities()
        print("Daily report (part 3) completed\n")
        return msg
        
    except Exception as e:
        print(f"Failed to generate daily report: {str(e)}\n")
        raise
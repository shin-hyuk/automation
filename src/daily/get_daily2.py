import btc
import crypto

def get_daily2():
    msg = btc.get_chain()
    msg += "\n" + btc.get_etf()
    msg += "\n" + btc.get_world_liberty()

    return msg
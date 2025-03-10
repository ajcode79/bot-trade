import ccxt
import pandas as pd
import pandas_ta as ta
import time
import threading
#---------------------------------
#محل قرارگیری اطلاعات وبسرویس صرافی مکسی
API_KEY = "mx0vglX7SejBbX"
API_SECRET = "a57712d32dcf145c8ccdc5"
#---------------------------------
exchange = ccxt.mexc({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'recvWindow': 60000}
})

symbols = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT",
    "LTC/USDT", "LINK/USDT", "ATOM/USDT", "ETC/USDT", "UNI/USDT",
    "BCH/USDT", "XLM/USDT", "FIL/USDT", "ICP/USDT", "APT/USDT"
]
#---------------------------------
#محل قرارگیری درصد سرمایه برای هر معامله
trade_percentage = 1.0  
#---------------------------------
current_trade = None  
stop_monitoring = False  

def get_balance():
    """ دریافت موجودی USDT """
    balance = exchange.fetch_balance()
    return balance['USDT']['free']

def calculate_tp_sl(symbol):
    """ تعیین حد سود و حد ضرر بر اساس ATR """
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        atr = ta.atr(df["high"], df["low"], df["close"], length=14).iloc[-1]
        last_price = df["close"].iloc[-1]
        #---------------------------------
        tp_price = last_price + (1.8 * atr)  # افزایش حد سود برای کاهش ضررهای سریع
        sl_price = last_price - (1.0 * atr)  # کاهش حد ضرر برای محافظت از سرمایه
        #---------------------------------

        return tp_price, sl_price
    except Exception as e:
        print(f"❌ خطا در محاسبه حد سود و ضرر: {e}")
        return None, None

def get_best_symbol():
    """ یافتن بهترین ارز برای خرید بر اساس RSI، EMA و حجم معاملات """
    best_symbol, best_rsi = None, 0

    for symbol in symbols:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            df["rsi"] = ta.rsi(df["close"], length=14)
            df["ema"] = ta.ema(df["close"], length=20)
            df["volume_ma"] = df["volume"].rolling(window=10).mean()

            last_rsi, last_price, last_ema, last_vol, avg_vol = df["rsi"].iloc[-1], df["close"].iloc[-1], df["ema"].iloc[-1], df["volume"].iloc[-1], df["volume_ma"].iloc[-1]

            print(f"🔍 {symbol} | قیمت: {last_price:.2f} | RSI: {last_rsi:.2f} | EMA: {last_ema:.2f} | حجم: {last_vol:.2f}")

            if last_rsi < 50 and last_price < last_ema and last_vol > avg_vol and last_rsi > best_rsi:
                best_rsi, best_symbol = last_rsi, symbol
        except Exception as e:
            print(f"❌ خطا در دریافت داده‌های {symbol}: {e}")

    return best_symbol

def place_order(symbol):
    """ انجام خرید و تنظیم حد سود و ضرر """
    global current_trade

    try:
        usdt_balance = get_balance()
        trade_amount = usdt_balance * trade_percentage

        if trade_amount < 5:
            print("⚠️ موجودی کافی نیست.")
            return

        ticker = exchange.fetch_ticker(symbol)
        price, amount = ticker['last'], trade_amount / ticker['last']

        tp_price, sl_price = calculate_tp_sl(symbol)
        if not tp_price or not sl_price:
            print("⚠️ نتوانستیم حد سود و ضرر را تعیین کنیم.")
            return

        exchange.create_market_buy_order(symbol, amount)
        print(f"✅ خرید انجام شد: {symbol} | قیمت: {price} | مقدار: {amount}")
        print(f"🎯 حد سود: {tp_price:.4f} | 🛑 حد ضرر: {sl_price:.4f}")

        current_trade = (symbol, amount, price, tp_price, sl_price)

    except Exception as e:
        print(f"❌ خطا در ثبت سفارش: {e}")

def monitor_trade():
    """ بررسی و بستن معامله در صورت نیاز """
    global current_trade, stop_monitoring

    if not current_trade:
        return

    symbol, amount, buy_price, take_profit_price, stop_loss_price = current_trade

    while not stop_monitoring:
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']

        print(f"🔍 بررسی قیمت {symbol}: {current_price:.4f}")
        balance = exchange.fetch_balance()
        asset = symbol.split('/')[0]
        available_amount = balance[asset]['free']

        if current_price >= take_profit_price:
            exchange.create_market_sell_order(symbol, available_amount)
            profit = (current_price - buy_price) * available_amount
            print(f"✅ فروش با سود انجام شد! سود: {profit:.2f} USDT")
            current_trade = None
            return

        elif current_price <= stop_loss_price:
            exchange.create_market_sell_order(symbol, available_amount)
            loss = (buy_price - current_price) * available_amount
            print(f"🛑 فروش با ضرر انجام شد! ضرر: {loss:.2f} USDT")
            current_trade = None
            return

        time.sleep(10)

def user_input_listener():
    """ کنترل دستی برای بستن معامله """
    global stop_monitoring, current_trade

    while True:
        command = input("📝 برای بستن معامله end را تایپ کنید یا continue برای ادامه: ").strip().lower()
        if command == "end" and current_trade:
            stop_monitoring = True
            time.sleep(2)
            symbol, amount, buy_price, _, _ = current_trade

            balance = exchange.fetch_balance()
            asset = symbol.split('/')[0]
            available_amount = balance[asset]['free']

            ticker = exchange.fetch_ticker(symbol)
            sell_price = ticker['last']

            exchange.create_market_sell_order(symbol, available_amount)
            profit_or_loss = (sell_price - buy_price) * available_amount
            result = "✅ سود" if profit_or_loss > 0 else "🛑 ضرر"
            print(f"{result}: {profit_or_loss:.2f} USDT")

            current_trade = None
            stop_monitoring = False


input_thread = threading.Thread(target=user_input_listener)
input_thread.start()

while True:
    if current_trade is None:
        print("\n🚀 بررسی بازار برای پیدا کردن بهترین فرصت معامله...")
        best_trade = get_best_symbol()

        if best_trade:
            place_order(best_trade)
            monitor_trade()
        else:
            print("⏳ هیچ ارز مناسبی برای خرید پیدا نشد.")
#---------------------------------
#source bot trade v1
#---------------------------------
#coded by ajcode79
#---------------------------------
    time.sleep(5)

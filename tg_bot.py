import threading
import time
import datetime
import redis

from retry import retry
import telebot
import schedule
from telebot import types
from dotenv import load_dotenv
import os
from binance.client import Client
import requests

load_dotenv()
TAAPI_SECRET = os.getenv("TAAPI-SECRET")

bot = telebot.TeleBot(os.getenv("BOT-TOKEN"))
redis_client = redis.from_url(os.getenv("REDISCLOUD_URL"))
key_ttl = 86400
API_KEY = None
API_SECRET = None
user_id = 0


@bot.message_handler(commands=["start"])  # початкова команда
def start(message):
    global user_id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("🇺🇦 Українська")
    btn2 = types.KeyboardButton("🇬🇧 English")
    markup.add(btn1, btn2)
    bot.send_message(
        message.from_user.id,
        "🇺🇦 Виберіть мову / 🇬🇧 Choose your language",
        reply_markup=markup,
    )


@bot.message_handler(content_types=["text"])
def get_text_messages(message):
    # Українська мова
    if message.text == "🇺🇦 Українська":
        bot.send_message(
            message.from_user.id,
            "👋 Вас вітає бот для трейдингу на біржі Binance",
            reply_markup=create_basic_markup(),
        )
        bot.send_message(message.from_user.id, "👀 Виберіть потрібний вам розділ")

    elif message.text == "🔙 Повернутися до вибору мови":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn1 = types.KeyboardButton("🇺🇦 Українська")
        btn2 = types.KeyboardButton("🇬🇧 English")
        markup.add(btn1, btn2)
        bot.send_message(
            message.from_user.id,
            "🇺🇦 Виберіть мову / 🇬🇧 Choose your language",
            reply_markup=markup,
        )

    # Автентифікація
    elif message.text == "🔐 Автентифікація":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn1 = types.KeyboardButton("🏁 Почати Автентифікацію")
        btn2 = types.KeyboardButton("⚠️ Допомога Автентифікації")
        btn3 = types.KeyboardButton("🔙 Головне меню")
        markup.add(btn1, btn2, btn3)
        bot.send_message(message.from_user.id, "⬇ Виберіть розділ", reply_markup=markup)

    elif message.text == "🏁 Почати Автентифікацію":
        bot.send_message(
            message.from_user.id,
            "Введіть API ключ та secret ключ через кому (наприклад, API_KEY,API_SECRET)",
        )
        bot.register_next_step_handler(message, get_keys)

    # Операції з бінанс
    elif message.text == "💰 Баланс":
        if not API_KEY or not API_SECRET:
            bot.send_message(message.from_user.id, "Спочатку введіть API ключ і secret ключ.")
            return
        client = Client(API_KEY, API_SECRET)
        account_info = client.get_account()
        balance_text = ""
        for balance in account_info["balances"]:
            if float(balance["free"]) > 0:
                asset = balance["asset"]
                padding = " " * (5 - len(asset))
                balance_text += f"\n{asset}{padding}➡️ Доступно: {balance['free']} 💰\n"
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn = types.KeyboardButton("🔙 Головне меню")
        markup.add(btn)
        bot.send_message(
            message.from_user.id,
            f"\n{balance_text}",
            parse_mode="Markdown",
            reply_markup=markup,
        )

    elif message.text == "💸 Переглянути прайс":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn = types.KeyboardButton("🔙 Головне меню")
        markup.add(btn)
        bot.send_message(message.from_user.id, "⬇ Виберіть розділ", reply_markup=markup)

    # Операції з бінанс
    elif message.text == "⚠️ Допомога":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn = types.KeyboardButton("🔙 Головне меню")
        markup.add(btn)
        bot.send_message(message.from_user.id, "⬇ Виберіть розділ", reply_markup=markup)

    elif message.text == "🔙 Головне меню":
        bot.send_message(
            message.from_user.id,
            "👀 Виберіть потрібний вам розділ",
            reply_markup=create_basic_markup(),
        )

    elif message.text == "Start trading":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn = types.KeyboardButton("🔙 Головне меню")
        markup.add(btn)
        bot.send_message(message.from_user.id, "⬇ Виберіть розділ", reply_markup=markup)
        global key_ttl
        binanceSymbol = "ICPUSDT"
        if not redis_client.exists(binanceSymbol):
            refreshState(binanceSymbol)
        # schedule.every(2).seconds.do(lambda: trade("SOL", "USDT", 0.06, 0.52))
        schedule.every(2).seconds.do(lambda: trade("ICP", "USDT", 6, 0.05))
        run_continuously()

    elif message.text == "Stop all tradings":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn = types.KeyboardButton("🔙 Головне меню")
        markup.add(btn)
        bot.send_message(message.from_user.id, "⬇ Виберіть розділ", reply_markup=markup)
        schedule.clear()
        refreshState("ICPUSDT")

    elif message.text == "Get futures notification":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn = types.KeyboardButton("🔙 Головне меню")
        markup.add(btn)

        def send_rsi_notification():
            try:
                rsi14 = futures()
                rsi = int(rsi14[0]["value"])
                if rsi is not None:
                    if rsi < 15:
                        bot.send_message(message.from_user.id, "RSI is below 15! SOL/USDT Time 1m")
                        time.sleep(120)
                    elif rsi > 65:
                        bot.send_message(message.from_user.id, "RSI is above 65! SOL/USDT Time 1m")
                        time.sleep(120)
            except Exception as ex:
                print("Caught exception.")
                print(ex)

        schedule.every(8).seconds.do(send_rsi_notification)
        run_continuously()


def refreshState(key):
    if redis_client.exists(key):
        redis_client.delete(key)
    redis_client.hset(key, mapping={"last_action": "sell", "last_buy_price": 0, "last_sell_price": 0})
    redis_client.expire(name=key, time=key_ttl)


def create_basic_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("🔐 Автентифікація")
    btn2 = types.KeyboardButton("💰 Баланс")
    btn3 = types.KeyboardButton("💸 Переглянути прайс")
    btn4 = types.KeyboardButton("⚠️ Допомога")
    btn5 = types.KeyboardButton("🔙 Повернутися до вибору мови")
    btn6 = types.KeyboardButton("Start trading")
    btn7 = types.KeyboardButton("Stop all tradings")
    btn8 = types.KeyboardButton("Get futures notification")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8)
    return markup

def get_keys(message):
    global API_KEY, API_SECRET, user_id
    keys = message.text.split(",")
    if len(keys) != 2:
        bot.send_message(
            message.from_user.id,
            "Введіть API ключ та secret ключ через кому (наприклад, API_KEY,API_SECRET)",
        )
        bot.register_next_step_handler(message, get_keys)
    else:
        API_KEY, API_SECRET = keys
        user_id = message.from_user.id
        bot.send_message(message.from_user.id, "Автентифікація пройдена успішно!✅")


def run_continuously(interval=1):
    cease_continuous_run = threading.Event()

    class ScheduleThread(threading.Thread):
        @classmethod
        def run(cls):
            while not cease_continuous_run.is_set():
                schedule.run_pending()
                time.sleep(interval)

    continuous_thread = ScheduleThread()
    continuous_thread.start()
    return cease_continuous_run


def trade(fromCoin, toCoin, quantity, sell_amount):
    try:
        global API_KEY, API_SECRET
        client = Client(API_KEY, API_SECRET)
        # klines = client.get_klines(symbol=binanceSymbol, interval="5m", limit=2)
        binanceSymbol = f"{fromCoin}{toCoin}"
        current_price = callWithRetry(client.get_symbol_ticker, symbol=binanceSymbol)["price"]
        encoded_state = redis_client.hgetall(binanceSymbol)
        state = {key.decode('utf-8'): value.decode('utf-8') for key, value in encoded_state.items()}

        if state["last_action"] == "sell":
            rsi6 = getFuturesData(f"{fromCoin}/{toCoin}", "1m", 2, 3)
            last_rsi = rsi6[1]["value"]
            if last_rsi < 20:
                redis_client.hset('my_hash', 'last_action', 'buy')
                state["last_action"] = "buy"
                state["last_buy_price"] = current_price
                response = callWithRetry(client.order_market_buy, symbol=binanceSymbol, quantity=quantity)
                buy_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                buyMessage = f"Buy {fromCoin} at {current_price} at {buy_time} rsi {last_rsi}"
                callWithRetry(bot.send_message, user_id, buyMessage)
                print(buyMessage)

        if state["last_action"] == "buy" and float(current_price) > float(state["last_buy_price"]) + sell_amount:
            response = callWithRetry(client.order_market_sell, symbol=binanceSymbol, quantity=quantity)
            sell_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            profit = float(current_price) - float(state["last_buy_price"])
            sellMessage = f"Sell {fromCoin} at {current_price} at {sell_time}.\nProfit: {profit}"
            callWithRetry(bot.send_message, user_id, sellMessage)
            print(sellMessage)
            state["last_action"] = "sell"
            state["last_sell_price"] = current_price

        redis_client.hset(binanceSymbol, mapping=state)
        global key_ttl
        redis_client.expire(binanceSymbol,  key_ttl)
    except Exception as ex:
        print("Caught exception.", datetime.datetime.now())
        print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print(ex)


@retry(Exception, tries=5, delay=5)
def getTapiData(symbol, interval, backtracks, period):
    api_url = f"https://api.taapi.io/ema?secret={TAAPI_SECRET}&exchange=binance&symbol={symbol}&interval={interval}&backtracks={backtracks}&period={period}"
    response = requests.get(api_url)
    return response.json()

@retry(Exception, tries=5, delay=5)
def callWithRetry(func, *args, **kwargs):
    return func(*args, **kwargs)


def futures():
    try:
        rsi14_SOL_USDT = getFuturesData("SOL/USDT", "1m", 2, 14)
        return rsi14_SOL_USDT
    except Exception as ex:
        print("Caught exception.")
        print(ex)
        return None


@retry(tries=5, delay=5)
def getFuturesData(symbol, interval, backtracks, period):
    api_url = f"https://api.taapi.io/rsi?secret={TAAPI_SECRET}&exchange=binance&symbol={symbol}&interval={interval}&backtracks={backtracks}&period={period}"
    response = requests.get(api_url)
    return response.json()


bot.polling(none_stop=True, interval=0)

# торг на лініях ма
# def trade():
#     try:
#         global API_KEY, API_SECRET
#         ema9 = getTapiData("SOL/USDT", "1m", 2, 9)
#         ema20 = getTapiData("SOL/USDT", "1m", 2, 20)
#         rsi14 = getFuturesData("SOL/USDT", "1m", 2, 14)
#         client = Client(API_KEY, API_SECRET)
#         e = 0.0005
#         last_ema9 = ema9[0]["value"]
#         prev_ema9 = ema9[1]["value"]
#         last_ema20 = ema20[0]["value"]
#         prev_ema20 = ema20[1]["value"]
#         last_rsi = rsi14[0]["value"]
#         if not hasattr(trade, "last_action"):
#             trade.last_action = "sell"
#
#         if prev_ema9 < prev_ema20 and last_ema9 > last_ema20 and last_rsi < 70 and trade.last_action != "buy":
#             current_price = client.get_symbol_ticker(symbol="SOLUSDT")["price"]
#             # response = client.order_market_buy(symbol="SOLUSDT", quantity=0.2)
#             buy_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#             print(f"Buy SOL at {current_price} at {buy_time}")
#             trade.last_action = "buy"
#             trade.last_buy_price = current_price
#         elif prev_ema9 > prev_ema20 and last_ema9 < last_ema20 and last_rsi > 30 and trade.last_action != "sell":
#             current_price = client.get_symbol_ticker(symbol="SOLUSDT")["price"]
#             # response = client.order_market_sell(symbol="SOLUSDT", quantity=0.2)
#             sell_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#             print(f"Sell SOL at {current_price} at {sell_time}")
#             trade.last_action = "sell"
#             trade.last_sell_price = current_price
#             profit = float(current_price) - float(trade.last_buy_price)
#             print(f"Profit: {profit}")
#     except Exception as ex:
#         print("Caught exception.")
#         print(ex)

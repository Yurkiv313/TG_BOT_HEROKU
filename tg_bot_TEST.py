import json
import uuid
import datetime
import telebot
import threading
import time
from datetime import datetime
import pytz
import redis

from retry import retry
import schedule
from telebot import types
from dotenv import load_dotenv
import os
from binance.client import Client
import requests

from coin_message_publisher import MessagePublisher
from message_manager import Message

load_dotenv()
TAAPI_SECRET = os.getenv("TAAPI-SECRET")

bot = telebot.TeleBot(os.getenv("BOT-TOKEN"))
redis_client = redis.from_url(os.getenv("REDISCLOUD_URL"))
key_ttl = 86400
API_KEY = None
API_SECRET = None
user_id = 0
publisher = MessagePublisher()
from_coin = 'USDT'
to_coin = 'UAH'
minutes_time_interval = "1m"


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
            bot.send_message(
                message.from_user.id, "Спочатку введіть API ключ і secret ключ."
            )
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
        binanceSymbol = from_coin + to_coin
        if not redis_client.exists(f"{binanceSymbol}-AY_TEST"):
            initial_state = {
                "last_action": "",
                "last_buy_price": "",
                "last_sell_price": "",
            }
            redis_client.hmset(f"{binanceSymbol}-AY_TEST", initial_state)
        # schedule.every(2).seconds.do(lambda: trade("SOL", "USDT", 0.06, 0.52))
        schedule.every(3).seconds.do(lambda: trade(from_coin, to_coin, 6, 0.05)).tag(
            "Trading job"
        )
        run_continuously()

    elif message.text == "Stop all tradings":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn = types.KeyboardButton("🔙 Головне меню")
        markup.add(btn)
        bot.send_message(message.from_user.id, "⬇ Виберіть розділ", reply_markup=markup)
        schedule.clear()
        binanceSymbol = from_coin + to_coin
        refreshState(f"{binanceSymbol}-AY_TEST")

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
                        bot.send_message(
                            message.from_user.id, "RSI is below 15! SOL/USDT Time 1m"
                        )
                        time.sleep(120)
                    elif rsi > 65:
                        bot.send_message(
                            message.from_user.id, "RSI is above 65! SOL/USDT Time 1m"
                        )
                        time.sleep(120)
            except Exception as ex:
                print("Caught exception.")
                print(ex)

        schedule.every(8).seconds.do(send_rsi_notification).tag("Futures")
        run_continuously()

    elif message.text == "Get active workers":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn = types.KeyboardButton("🔙 Головне меню")
        markup.add(btn)

        all_jobs = schedule.get_jobs()
        new_list = [",".join(map(str, x.tags)) for x in all_jobs]
        bot.send_message(
            message.from_user.id,
            str("\n".join(new_list))
            if len(new_list) != 0
            else "There are no active jobs.",
        )


def refreshState(key):
    if redis_client.exists(key):
        redis_client.delete(key)
    redis_client.hset(
        key, mapping={"last_action": "sell", "last_buy_price": 0, "last_sell_price": 0}
    )
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
    btn9 = types.KeyboardButton("Get active workers")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9)
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
        id = uuid.uuid4()
        print("Start job", id)
        global API_KEY, API_SECRET
        client = Client(API_KEY, API_SECRET)
        # klines = client.get_klines(symbol=binanceSymbol, interval="5m", limit=2)
        binance_symbol = f"{fromCoin}{toCoin}"
        current_price = float(
            callWithRetry(client.get_symbol_ticker, symbol=binance_symbol)["price"]
        )
        print("current_price = ", current_price, id)
        encoded_state = redis_client.hgetall(f"{binance_symbol}-AY_TEST")
        state = {
            key.decode("utf-8"): value.decode("utf-8")
            for key, value in encoded_state.items()
        }

        if state["last_action"] == "sell":
            stoch_rsi = getIndicatorValue("stochrsi", f"{fromCoin}/{toCoin}", minutes_time_interval, 5)
            print("Buy operation started", id)
            print("StochRsi FastD line = ", stoch_rsi, id)
            last_rsi_d = stoch_rsi[1]["valueFastD"]  # yellow line
            last_rsi_k = stoch_rsi[1]["valueFastK"]
            current_rsi_k = stoch_rsi[0]["valueFastK"]  # blue line

            before_last_rsi_d = stoch_rsi[2]["valueFastD"]  # yellow line
            before_last_rsi_k = stoch_rsi[2]["valueFastK"]

            if ((last_rsi_d < 14 and last_rsi_k < 14) and current_rsi_k > 21) or (before_last_rsi_d < 20 and before_last_rsi_k < 20 and last_rsi_k > 20):
            # if last_rsi_d < 100:
                # adx_indicator = getIndicatorValue('adx', f"{fromCoin}/{toCoin}", minutes_time_interval, 2, 14)
                # last_adx = adx_indicator[1]["value"]
                macd_indicator = getIndicatorValue(
                    "macd", f"{fromCoin}/{toCoin}", minutes_time_interval, 16
                )
                negative_hists = [x for x in macd_indicator if x["valueMACDHist"] < 0]
                last_macd_hist = macd_indicator[1]["valueMACDHist"]

                # if len(negative_hists) != len(macd_indicator) and last_macd_hist < 0.001:
                print("macd_indicator = ", macd_indicator, id)
                # second_before_last_macd_hist = macd_indicator[3]["valueMACDHist"]
                # before_last_macd_hist = macd_indicator[2]["valueMACDHist"]
                # last_macd_hist = macd_indicator[1]["valueMACDHist"]
                # current_forming_macd_hist = macd_indicator[0]["valueMACDHist"]
                # is_macd_hist_negative = second_before_last_macd_hist < 0 and before_last_macd_hist < 0 and last_macd_hist < 0
                # is_last_macd_lower_than_two_before = current_forming_macd_hist > last_macd_hist > before_last_macd_hist

                # negativeMacdDecreased = is_macd_hist_negative and is_last_macd_lower_than_two_before
                # last_macd = macd_indicator[1]["valueMACD"]
                last_macd_signal = macd_indicator[1]["valueMACDSignal"]
                # last_macd_diff = last_macd - last_macd_signal
                # last_madc_hist = macd_indicator[1]["valueMACDHist"]
                # if negativeMacdDecreased:
                last_madc_value = macd_indicator[1]["valueMACD"]
                state["last_action"] = "buy"
                state["last_buy_price"] = current_price
                # response = callWithRetry(client.order_market_buy, symbol=binanceSymbol, quantity=quantity)
                # buy_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ukraine_tz = pytz.timezone("Europe/Kiev")
                ukraine_time = datetime.now(ukraine_tz)
                ukraine_time_str = ukraine_time.strftime("%Y-%m-%d %H:%M:%S %Z")
                message = Message(
                    user_id=user_id,
                    coin=binance_symbol,
                    current_coin_price=current_price,
                    quantity=quantity,
                    last_action=state["last_action"],
                    created_date=ukraine_time_str,
                    last_stoch_rsi_k=last_rsi_k,
                    last_macd_value=last_madc_value,
                    last_macd_signal=last_macd_signal,
                    last_macd_hist=last_macd_hist,
                )
                message_json = json.dumps(vars(message))
                callWithRetry(bot.send_message, user_id, message_json)
                publisher.send_message(message_json)
                print(message_json)
                # обєкт для відправки в ребіт
        elif state["last_action"] == "buy":
            print("Sell operation started", id)
            macd_indicator = getIndicatorValue(
                "macd", f"{fromCoin}/{toCoin}", minutes_time_interval, 3, 3
            )
            print(f"id = {id}; macd_indicator = {macd_indicator}")

            before_last_macd_hist = macd_indicator[2]["valueMACDHist"]
            last_macd_hist = macd_indicator[1]["valueMACDHist"]
            positiveMacdIncreased = 0 < last_macd_hist < before_last_macd_hist

        if state["last_action"] == "buy" and float(current_price) > float(state["last_buy_price"]) + sell_amount:
            # response = callWithRetry(client.order_market_sell, symbol=binanceSymbol, quantity=quantity)
            sell_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            profit = (float(current_price) - float(state["last_buy_price"])) * quantity
            sell_message = f"Sell {fromCoin} at {current_price} at {sell_time}.\nProfit: {profit}."
            callWithRetry(bot.send_message, user_id, sell_message)
            print(sell_message)
            state["last_action"] = "sell"
            state["last_sell_price"] = current_price

        redis_client.hset(f'{binance_symbol}-TEST', mapping=state)
        global key_ttl
        redis_client.expire(f'{binance_symbol}-TEST', key_ttl)
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
        rsi14_SOL_USDT = getIndicatorValue("SOL/USDT", "1m", 2, 14)
        return rsi14_SOL_USDT
    except Exception as ex:
        print("Caught exception.")
        print(ex)
        return None


@retry(tries=5, delay=5)
def getIndicatorValue(indicator, symbol, interval, backtracks, period=3, k_period=3):
    api_url = f"https://api.taapi.io/{indicator}?secret={TAAPI_SECRET}&exchange=binance&symbol={symbol}&interval={interval}&backtracks={backtracks}&period={period}&kPeriod={k_period}"
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

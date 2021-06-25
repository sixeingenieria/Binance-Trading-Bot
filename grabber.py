# use if needed to pass args to external modules
import sys

# used to create threads & dynamic loading of modules
import threading
import importlib

# used for directory handling
import glob

#gogo MOD telegram needs import request
import requests

# needed for the binance API / websockets / Exception handling
from binance.client import Client
from binance.exceptions import BinanceAPIException
from requests.exceptions import ReadTimeout, ConnectionError

# used for dates
from datetime import date, datetime, timedelta
import time

# Load helper modules
from helpers.parameters import (
    parse_args, load_config
)

# Load creds modules
from helpers.handle_creds import (
    load_correct_creds, test_api_key,
    load_telegram_creds
)

def get_symbol_info(url='https://api.binance.com/api/v3/exchangeInfo'):
    global session_struct
    response = requests.get(url)
    json_message = json.loads(response.content)

    for symbol_info in json_message['symbols']:
        session_struct['symbol_info'][symbol_info['symbol']] = symbol_info['filters'][2]['stepSize']


def get_historical_price():
    global session_struct
    if is_fiat():
        session_struct['market_price'] = 1
        session_struct['exchange_symbol'] = PAIR_WITH
    else:
        session_struct['exchange_symbol'] = PAIR_WITH + 'USDT'
        market_historic = client.get_historical_trades(symbol=session_struct['exchange_symbol'])
        session_struct['market_price'] = market_historic[0].get('price')

def get_price(add_to_historical=True):
    '''Return the current price for all coins on binance'''

    global historical_prices, hsp_head, session_struct

    initial_price = {}
    prices = client.get_all_tickers()

    for coin in prices:
        if CUSTOM_LIST:
            if any(item + PAIR_WITH == coin['symbol'] for item in tickers) and all(item not in coin['symbol'] for item in EXCLUDED_PAIRS):
                initial_price[coin['symbol']] = { 'price': coin['price'], 'time': datetime.now()}
        else:
            if PAIR_WITH in coin['symbol'] and all(item not in coin['symbol'] for item in EXCLUDED_PAIRS):
                initial_price[coin['symbol']] = { 'price': coin['price'], 'time': datetime.now()}

    if add_to_historical:
        hsp_head += 1

        if hsp_head == 2:
            hsp_head = 0

        historical_prices[hsp_head] = initial_price

    return initial_price


def wait_for_price(type):
    '''calls the initial price and ensures the correct amount of time has passed
    before reading the current price again'''

    global historical_prices, hsp_head, volatility_cooloff, session_struct, settings_struct

    session_struct['market_resistance'] = 0
    session_struct['market_support'] = 0

    volatile_coins = {}
    externals = {}

    coins_up = 0
    coins_down = 0
    coins_unchanged = 0

    current_time_minutes = float(round(time.time()))/60

    pause_bot()

    #first time we just skip untill we find a way for historic fata to be grabbed here
    if session_struct['price_timedelta'] == 0: session_struct['price_timedelta'] = current_time_minutes
    #we give local variable value of time that we use for checking to grab prices again
    price_timedelta_value = session_struct['price_timedelta']

    #if historical_prices[hsp_head]['BNB' + PAIR_WITH]['time'] > datetime.now() - timedelta(minutes=float(TIME_DIFFERENCE / RECHECK_INTERVAL)):

        # sleep for exactly the amount of time required
        #time.sleep((timedelta(minutes=float(TIME_DIFFERENCE / RECHECK_INTERVAL)) - (datetime.now() - historical_prices[hsp_head]['BNB' + PAIR_WITH]['time'])).total_seconds())
    #print(f'PRICE_TIMEDELTA: {price_timedelta_value} - CURRENT_TIME: {current_time_minutes} - TIME_DIFFERENCE: {TIME_DIFFERENCE}')

    if session_struct['price_timedelta'] < current_time_minutes - float(settings_struct['TIME_DIFFERENCE']):

       #print(f'GET PRICE TRIGGERED !!!!! PRICE_TIMEDELTA: {price_timedelta_value} - TIME_DIFFERENCE: {TIME_DIFFERENCE}')
       # retrieve latest prices
       get_price()
       externals = external_signals()
       session_struct['price_timedelta'] = current_time_minutes


    # calculate the difference in prices
    for coin in historical_prices[hsp_head]:

        # minimum and maximum prices over time period
        min_price = min(historical_prices, key = lambda x: float("inf") if x is None else float(x[coin]['price']))
        max_price = max(historical_prices, key = lambda x: -1 if x is None else float(x[coin]['price']))

        threshold_check = (-1.0 if min_price[coin]['time'] > max_price[coin]['time'] else 1.0) * (float(max_price[coin]['price']) - float(min_price[coin]['price'])) / float(min_price[coin]['price']) * 100

        if threshold_check > 0:
            session_struct['market_resistance'] = session_struct['market_resistance'] + threshold_check
            coins_up = coins_up +1
        else:
            session_struct['market_support'] = session_struct['market_support'] - threshold_check
            coins_down = coins_down +1

        if type == 'percent_mix_signal':

           # each coin with higher gains than our CHANGE_IN_PRICE is added to the volatile_coins dict if less than TRADE_SLOTS is not reached.
           if threshold_check > settings_struct['CHANGE_IN_PRICE_MIN'] and threshold_check < settings_struct['CHANGE_IN_PRICE_MAX']:
               coins_up +=1


               #if os.path.exists('signals/nigec_custsignalmod.exs') or os.path.exists('signals/djcommie_custsignalmod.exs') or os.path.exists('signals/firewatch_signalsample.exs'):
               #signals = glob.glob("signals/*.exs")

               for excoin in externals:
                   #print(f'EXCOIN: {excoin}')
                   if excoin == coin:
                     # print(f'EXCOIN: {excoin} == COIN: {coin}')
                      if coin not in volatility_cooloff:
                         volatility_cooloff[coin] = datetime.now() - timedelta(minutes=settings_struct['TIME_DIFFERENCE'])
                      # only include coin as volatile if it hasn't been picked up in the last TIME_DIFFERENCE minutes already
                      if datetime.now() >= volatility_cooloff[coin] + timedelta(minutes=settings_struct['TIME_DIFFERENCE']):
                         volatility_cooloff[coin] = datetime.now()
                         if len(coins_bought) + len(volatile_coins) < TRADE_SLOTS or TRADE_SLOTS == 0:
                            volatile_coins[coin] = round(threshold_check, 3)
                            print(f"{coin} has gained {volatile_coins[coin]}% within the last {settings_struct['TIME_DIFFERENCE']} minutes, and coin {excoin} recived a signal... calculating {QUANTITY} {PAIR_WITH} value of {coin} for purchase!")
                         #else:
                            #print(f"{txcolors.WARNING}{coin} has gained {round(threshold_check, 3)}% within the last {TIME_DIFFERENCE} minutes, , and coin {excoin} recived a signal... but you are using all available trade slots!{txcolors.DEFAULT}")


        if type == 'percent_and_signal':

            # each coin with higher gains than our CHANGE_IN_PRICE is added to the volatile_coins dict if less than TRADE_SLOTS is not reached.
            if threshold_check > settings_struct['CHANGE_IN_PRICE_MIN'] and threshold_check < settings_struct['CHANGE_IN_PRICE_MAX']:
                coins_up +1

                if coin not in volatility_cooloff:
                    volatility_cooloff[coin] = datetime.now() - timedelta(minutes=settings_struct['TIME_DIFFERENCE'])

                # only include coin as volatile if it hasn't been picked up in the last TIME_DIFFERENCE minutes already
                if datetime.now() >= volatility_cooloff[coin] + timedelta(minutes=settings_struct['TIME_DIFFERENCE']):
                    volatility_cooloff[coin] = datetime.now()

                if len(coins_bought) + len(volatile_coins) < TRADE_SLOTS or TRADE_SLOTS == 0:
                    volatile_coins[coin] = round(threshold_check, 3)
                    print(f"{coin} has gained {volatile_coins[coin]}% within the last {settings_struct['TIME_DIFFERENCE']} minutes {QUANTITY} {PAIR_WITH} value of {coin} for purchase!")

                #else:
                   #print(f"{txcolors.WARNING}{coin} has gained {round(threshold_check, 3)}% within the last {TIME_DIFFERENCE} minutes but you are using all available trade slots!{txcolors.DEFAULT}")

            externals = external_signals()
            exnumber = 0

            for excoin in externals:
                if excoin not in volatile_coins and excoin not in coins_bought and (len(coins_bought) + exnumber) < TRADE_SLOTS:
                    volatile_coins[excoin] = 1
                    exnumber +=1
                    print(f"External signal received on {excoin}, calculating {QUANTITY} {PAIR_WITH} value of {excoin} for purchase!")

        if threshold_check < settings_struct['CHANGE_IN_PRICE_MIN'] and threshold_check > settings_struct['CHANGE_IN_PRICE_MAX']:
             coins_down +=1

        else:
            coins_unchanged +=1

    if coins_up != 0: session_struct['market_resistance'] = session_struct['market_resistance'] / coins_up
    if coins_down != 0: session_struct['market_support'] = session_struct['market_support'] / coins_down

    if DETAILED_REPORTS == True and hsp_head:
        report('detailed',f"Market Resistance:      {txcolors.DEFAULT}{session_struct['market_resistance']:.4f}\n Market Support:         {txcolors.DEFAULT}{session_struct['market_support']:.4f}")
    else:
        report('console', f" MR:{session_struct['market_resistance']:.4f}/MS:{session_struct['market_support']:.4f} ")

    return volatile_coins, len(volatile_coins), historical_prices[hsp_head]

def test_order_id():
    import random
    """returns a fake order id by hashing the current time"""
    test_order_id_number = random.randint(100000000,999999999)
    return test_order_id_number
def extract_order_data(order_details):
    global TRADING_FEE, STOP_LOSS, TAKE_PROFIT
    transactionInfo = {}
    # adding order fill extractions here
    #
    # just to explain what I am doing here:
    # Market orders are not always filled at one price, we need to find the averages of all 'parts' (fills) of this order.
    #
    # reset other variables to 0 before use
    FILLS_TOTAL = 0
    FILLS_QTY = 0
    FILLS_FEE = 0
    BNB_WARNING = 0
    # loop through each 'fill':
    for fills in order_details['fills']:
        FILL_PRICE = float(fills['price'])
        FILL_QTY = float(fills['qty'])
        FILLS_FEE += float(fills['commission'])
        # check if the fee was in BNB. If not, log a nice warning:
        if (fills['commissionAsset'] != 'BNB') and (TRADING_FEE == 0.75) and (BNB_WARNING == 0):
            print(f"WARNING: BNB not used for trading fee, please ")
            BNB_WARNING += 1
        # quantity of fills * price
        FILLS_TOTAL += (FILL_PRICE * FILL_QTY)
        # add to running total of fills quantity
        FILLS_QTY += FILL_QTY
        # increase fills array index by 1

    # calculate average fill price:
    FILL_AVG = (FILLS_TOTAL / FILLS_QTY)

    tradeFeeApprox = (float(FILLS_QTY) * float(FILL_AVG)) * (TRADING_FEE/100)
    # create object with received data from Binance
    transactionInfo = {
        'symbol': order_details['symbol'],
        'orderId': order_details['orderId'],
        'timestamp': order_details['transactTime'],
        'avgPrice': float(FILL_AVG),
        'volume': float(FILLS_QTY),
        'tradeFeeBNB': float(FILLS_FEE),
        'tradeFee': tradeFeeApprox,
    }
    return transactionInfo

# recommend.py
import profile
import openai  #  OpenAI <= 1.0.0
import requests, openrouteservice, json, os, time,re
import pandas as pd
from collections import Counter, defaultdict
from datetime import datetime
from geopy.distance import geodesic
from flask import Flask, request, abort
from linebot import (LineBotApi, WebhookHandler)
from linebot.exceptions import (InvalidSignatureError)
from linebot.models import *

import tempfile, os,re
import datetime
import openai
import time
import traceback
# from openai import OpenAI OpenAI >= 1.0.0

API = os.getenv('GOOGLE_API_KEY')
OR_API_KEY = os.getenv('OR_API_KEY')
api_key = os.getenv('OPENAI_API_KEY')

# client = OpenAI(api_key = api_key) OpenAI >= 1.0.0
def remove_markdown(text):
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'\[(.*?)]\(.*?\)', r'\1', text)
    text = re.sub(r'^#+\s', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*-\s*', '', text, flags=re.MULTILINE)
    return text

def recommend_food_private():

    line_bot_api.reply_message(
        event.reply_token,
            TextSendMessage(text="now enter recommend_food_private()"),
    )

    
    # Type in the request
    address = input('Type in your address: ')

    num = int(input('Choose a number for your mode(1:walking, 2:driving, 3:delivering): '))
    minutes1 = int(input("Type in the minimum minute you want: "))
    mode, profile, minutes = together(num, minutes1)

    # profile = input('Type in your profile: ')
    # minutes = int(input("Type in the minimum minute you want: "))
    # mode = input('Type in your mode: ')

    # Applying the Google API
    start_time = time.time()
    lat, lng = transform(address)
    isochrone_data, max_dists = get_isochrone(lat, lng, profile, minutes * 60)

    a = find_restaurant(lat, lng, minutes, mode, max_dists)
    # print(a)
    end_time = time.time()
    print(f'{end_time - start_time:.2f} seconds')

    # Past data loading
    parsed_orders = read_data("transformed_orders_details.csv")
    favorite_foods = get_favorite_foods(parsed_orders)
    favorite_restaurants = get_favorite_restaurants(parsed_orders)
    avg_price, max_price, min_price = get_price_distribution(parsed_orders)
    weights = calculate_order_weight(parsed_orders, '2025/03/06')

    # Applying Openai API
    request = input('Type in your request: ')

    # 1. Rules for system
    system_message = """
    你是個優秀的個人飲食推薦助理，且中文是你的母語，請根據使用者的歷史訂單、最常點的食物、價格範圍與附近的餐廳資料，提供最佳的餐點建議。

    # Rules：
    1. 優先推薦點餐次數較多的食物，因為這代表使用者的偏好。
    2. 近期點過的品項比久遠的品項權重大，使用者的口味可能會改變。
    3. 確保推薦的餐點符合價格範圍，不要超出使用者的預算太多。
    4. 如果附近有使用者常去的餐廳，請優先推薦該餐廳的餐點。
    5. 如果沒有找到符合條件的歷史訂單，請根據附近的高評分餐廳來推薦。
    """

    # 2. Combine the rules, past_data, and restaurant_nearby
    full_system_message = f"""
    {system_message}

    # Past Order：
    {json.dumps(parsed_orders, ensure_ascii=False, indent=2)}

    # Favorite food：
    {json.dumps(favorite_foods, ensure_ascii=False, indent=2)}

    # Favorite restaurants：
    {json.dumps(favorite_restaurants, ensure_ascii=False, indent=2)}

    # avg_price, max_price, min_price：
    {json.dumps(avg_price, ensure_ascii=False, indent=2)}
    {json.dumps(max_price, ensure_ascii=False, indent=2)}
    {json.dumps(min_price, ensure_ascii=False, indent=2)}

    # weights accroding to different dates：
    {json.dumps(weights, ensure_ascii=False, indent=2)}

    # 這個檔案是我附近餐廳的資訊
    # Restaurants nearby：
    {json.dumps(a, ensure_ascii=False, indent=2)}

    請根據附近餐廳的資訊，根據我的喜好，推薦三間符合要求的餐廳，並推薦 1-2 道其餐廳中符合使用者偏好的餐點、其價格與卡路里，並解釋推薦的理由。
    """

    ans = openai_api(full_system_message, request)
    print(remove_markdown(ans))

# ------------------------------------------------------------------------------------------------------------------#
# Tool

def together(num, minutes):
    if num == 1:
        mode = 'walking'
        profile = 'foot-walking'
        minute = minutes
    elif num == 2:
        mode = 'driving'
        profile = 'driving-car'
        minute = minutes
    elif num == 3:
        mode = 'driving'
        profile = 'driving-car'
        minute = minutes
    return mode, profile, minute


# ------------------------------------------------------------------------------------------------------------------#
# Google API search restaurants

# transform the location to lat and lng

def transform(address):
    """將地址轉換成經緯度"""
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={API}"
    data = requests.get(url).json()
    if data.get('status') == 'OK':
        lat = data['results'][0]['geometry']['location']['lat']
        lng = data['results'][0]['geometry']['location']['lng']
        return lat, lng
    return None, None


# calculate the distance

def get_isochrone(lat, lng, profile, range_time):
    client = openrouteservice.Client(key=OR_API_KEY)

    location = [lng, lat]

    isochrone_result = client.isochrones(
        locations=[location],
        profile=profile,
        range=[range_time] if isinstance(range_time, (int, float)) else range_time
    )

    def get_max_distances(origin, isochrone):
        max_distances = []
        for feature in isochrone['features']:
            max_dist = 0
            for polygon in feature["geometry"]["coordinates"]:
                for point in polygon:
                    # calculate the distance
                    dist = geodesic((origin[1], origin[0]), (point[1], point[0])).m
                    max_dist = max(max_dist, dist)
            max_distances.append(max_dist)
        return max_distances

    # max distance
    max_distances = get_max_distances(location, isochrone_result)
    return isochrone_result, max_distances


def search_nearby(lat, lng, radius):
    """搜尋指定範圍內的所有餐廳"""
    url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius={radius}&type=restaurant&key={API}"
    restaurants = []

    while url:
        response = requests.get(url).json()
        if response.get('status') == 'OK':
            for place in response['results']:
                restaurants.append({
                    'name': place.get('name'),
                    'address': place.get('vicinity'),
                    'place_id': place.get('place_id'),
                    'rating': place.get('rating', 0),
                    'types': place.get('types')
                })
            next_page_token = response.get("next_page_token")
            if next_page_token:
                time.sleep(2)  # need 2 to 3 sec. to sleep
                url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?pagetoken={next_page_token}&key={API}"
            else:
                break
        else:
            break
    return restaurants


def find_restaurant(lat, lng, max_min, mode, radius):
    radius = radius[0]
    # radius = TIME_TO_RADIUS[mode](max_min)  # 根據時間計算半徑
    restaurants = search_nearby(lat, lng, radius)

    # Filter (Important)
    while len(restaurants) < 50 and radius < 20000:
        radius = int(radius * 1.2)  # 擴大 20%
        restaurants = search_nearby(lat, lng, radius)

    # Return All Restaurants
    return sorted(restaurants, key=lambda x: x["rating"], reverse=True)


# ------------------------------------------------------------------------------------------------------------------#
# Past Data Preprocessing

def read_data(file_name):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, 'transformed_orders_details.csv')
    
    df = pd.read_csv(file_path, sep=",", on_bad_lines="skip", engine="python")
    half = len(df) * 2 // 3
    df = df.iloc[:half]

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df.dropna(subset=["Date"], inplace=True)

    parsed_orders = []
    for _, row in df.iterrows():
        merchant = row["Merchant"]
        date = row["Date"].strftime("%Y/%m/%d")
        time = row["Time_24hr"]

        items = str(row["Item"]).split(";") if pd.notna(row["Item"]) else []

        prices = [float(p) for p in str(row["Price"]).split(";") if p.replace(".", "", 1).isdigit()]
        total_price = sum(prices) if prices else 0

        parsed_orders.append({
            "merchant": merchant,
            "date": date,
            "time": time,
            "items": items,
            "total_price": prices[0]
        })

    return parsed_orders


def get_favorite_foods(parsed_orders, top_n=30):
    all_items = [item for order in parsed_orders for item in order["items"]]
    return Counter(all_items).most_common(top_n)


def get_favorite_restaurants(parsed_orders, top_n=10):
    merchants = [order["merchant"] for order in parsed_orders]
    return Counter(merchants).most_common(top_n)


def get_price_distribution(parsed_orders):
    prices = [order["total_price"] for order in parsed_orders]
    avg_price = sum(prices) / len(prices)
    return avg_price, max(prices), min(prices)


def calculate_order_weight(parsed_orders, current_date):
    current_date = datetime.strptime(current_date, "%Y/%m/%d")
    weights = defaultdict(float)

    for order in parsed_orders:
        order_date = datetime.strptime(order["date"], "%Y/%m/%d")  # transform to date
        days_diff = (current_date - order_date).days  # find the difference between two dates

        if days_diff <= 7:
            weight = 1.0
        elif days_diff <= 30:
            weight = 0.5
        else:
            weight = 0.1

        weights[order["items"][0]] += weight

    return weights


# ------------------------------------------------------------------------------------------------------------------#

def openai_api(full_system_message, request):
    completion = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system",
             "content": full_system_message},
            {'role': 'user', 'content': request}
        ],
        temperature=0.7
    )
    return completion['choices'][0]['message']['content']
    # return completion.choices[0].message.content
    

# 主推薦函數

# def recommend_food(user_address, user_request, mode='walking', profile='foot-walking', minutes=15):
# def recommend_food(user_address, mode, minutes, user_request):
#     mode_mapping = {'walking':'foot-walking', 'driving':'driving-car'}
#     profile = mode_mapping.get(mode, 'foot-walking')
    
#     lat, lng = transform(user_address)
#     _, max_dists = get_isochrone(lat, lng, profile, minutes * 60)
#     restaurants = find_restaurant(lat, lng, minutes, mode, max_dists)

#     parsed_orders = read_data("transformed_orders_details.csv")
#     favorite_foods = get_favorite_foods(parsed_orders)
#     favorite_restaurants = get_favorite_restaurants(parsed_orders)
#     avg_price, max_price, min_price = get_price_distribution(parsed_orders)
#     weights = calculate_order_weight(parsed_orders, datetime.now().strftime('%Y/%m/%d'))

#     system_message = f"""
#     你是一個餐飲推薦助手。
#     # Rules：
#         1. 優先推薦點餐次數較多的食物。
#         2. 近期點過的品項比久遠的品項權重大。
#         3. 推薦價格應符合使用者平均消費約{avg_price}元，上限為{max_price}元。
#         4. 附近常去的餐廳優先。
#         5. 若無合適的歷史推薦，則以附近高評分餐廳推薦。

#     附近餐廳資訊：{restaurants[:10]}
#     喜好餐廳：{favorite_restaurants[:5]}
#     常點餐點：{favorite_foods[:10]}
#     價格區間：平均{avg_price}元，上限{max_price}元
#     """

#     answer = openai_api(system_message, user_request)
#     clean_answer = remove_markdown(answer)
#     return clean_answer


# def recommend_food(user_address, mode, minutes, user_request):
#     # user_request為使用者透過Line傳進來的訊息
#     result = recommend_food(user_request=user_request, user_address=user_address, mode=mode, profile=profile, minutes=minutes)
#     clean_result = remove_markdown(result)
#     return clean_result


# if __name__ == '__main__':
#     main()

# recommendation.py
import requests, openrouteservice, json, os, time, re
import pandas as pd
from collections import Counter, defaultdict
from datetime import datetime
from geopy.distance import geodesic
import openai

API = os.getenv('GOOGLE_API_KEY')
OR_API_KEY = os.getenv('OR_API_KEY')
openai.api_key = os.getenv('OPENAI_API_KEY')


def remove_markdown(text):
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'\[(.*?)]\(.*?\)', r'\1', text)
    text = re.sub(r'^#+\s', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*-\s*', '', text, flags=re.MULTILINE)
    return text


def transform(address):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={API}"
    data = requests.get(url).json()
    if data.get('status') == 'OK':
        lat = data['results'][0]['geometry']['location']['lat']
        lng = data['results'][0]['geometry']['location']['lng']
        return lat, lng
    return None, None


def get_isochrone(lat, lng, profile, range_time):
    client = openrouteservice.Client(key=OR_API_KEY)
    location = [lng, lat]
    isochrone_result = client.isochrones(locations=[location], profile=profile, range=[range_time])

    def get_max_distances(origin, isochrone):
        max_distances = []
        for feature in isochrone['features']:
            max_dist = 0
            for polygon in feature["geometry"]["coordinates"]:
                for point in polygon:
                    dist = geodesic((origin[1], origin[0]), (point[1], point[0])).m
                    max_dist = max(max_dist, dist)
            max_distances.append(max_dist)
        return max_distances

    max_distances = get_max_distances(location, isochrone_result)
    return isochrone_result, max_distances


def search_nearby(lat, lng, radius):
    url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius={radius}&type=restaurant&key={API}"
    response = requests.get(url).json()
    return response.get('results', [])


def find_restaurant(lat, lng, max_min, mode, radius):
    radius = radius[0]
    restaurants = search_nearby(lat, lng, radius)
    return sorted(restaurants, key=lambda x: x.get("rating", 0), reverse=True)


def read_data(file_name):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir,'transformed_orders_details.csv')
    df = pd.read_csv(file_path, sep=",", on_bad_lines="skip", engine="python")

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df.dropna(subset=["Date"], inplace=True)

    parsed_orders = []
    for _, row in df.iterrows():
        merchant = row["Merchant"]
        date = row["Date"].strftime("%Y/%m/%d")
        time = row["Time_24hr"]
        items = str(row["Item"]).split(";") if pd.notna(row["Item"]) else []
        prices = [float(p) for p in str(row["Price"]).split(";") if p.replace(".", "", 1).isdigit()]

        parsed_orders.append({"merchant": merchant, "date": date, "time": time, "items": items, "total_price": sum(prices)})

    return parsed_orders


def openai_api(full_system_message, request):
    completion = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": full_system_message},
            {"role": "user", "content": request}
        ],
        temperature=0.7
    )
    return completion['choices'][0]['message']['content']


def recommend_food(user_address, mode, minutes, user_request):
    profile = 'foot-walking' if mode == 'walking' else 'driving-car'
    lat, lng = transform(user_address)
    _, max_dists = get_isochrone(lat, lng, profile, minutes * 60)
    restaurants = find_restaurant(lat, lng, minutes, mode, max_dists)

    parsed_orders = read_data("transformed_orders_details.csv")
    favorite_foods = get_favorite_foods(parsed_orders)
    favorite_restaurants = get_favorite_restaurants(parsed_orders)
    avg_price, max_price, min_price = get_price_distribution(parsed_orders)
    weights = calculate_order_weight(parsed_orders, datetime.now().strftime('%Y/%m/%d'))

    system_message = f"""
    你是一個餐飲推薦助手。
    # Rules：
        1. 優先推薦點餐次數較多的食物。
        2. 近期點過的品項比久遠的品項權重大。
        3. 推薦價格應符合使用者平均消費約{avg_price}元，上限為{max_price}元。
        4. 附近常去的餐廳優先。
        5. 若無合適的歷史推薦，則以附近高評分餐廳推薦。

    附近餐廳資訊：{restaurants[:10]}
    喜好餐廳：{favorite_restaurants[:5]}
    常點餐點：{favorite_foods[:10]}
    價格區間：平均{avg_price}元，上限{max_price}元
    """

    answer = openai_api(system_message, user_request)
    return remove_markdown(answer)

if __name__ == '__main__':
    main()

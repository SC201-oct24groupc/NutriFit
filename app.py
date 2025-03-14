from flask import Flask, request, abort
from linebot import (LineBotApi, WebhookHandler)
from linebot.exceptions import (InvalidSignatureError)
from linebot.models import *
from recommendation import recommend_food_private
import tempfile, os,re
import datetime
import openai
import time
import traceback


app = Flask(__name__)
static_tmp_path = os.path.join(os.path.dirname(__file__), 'static', 'tmp')
# Channel Access Token
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
# Channel Secret
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
# OPENAI API Key初始化設定
openai.api_key = os.getenv('OPENAI_API_KEY')

def remove_markdown(text):
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    text = re.sub(r'^#+\s', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*-\s*', '', text, flags=re.MULTILINE)
    return text

def GPT_response(text):
    # 接收回應
    response = openai.ChatCompletion.create(
        model="gpt-4o", 
        messages=[{"role": "user", "content": text}],
        temperature=0.7, 
        max_tokens=500)
    print(response)
    # 重組回應
    answer = response['choices'][0]['message']['content'].strip()
    clean_answer = remove_markdown(answer)
    return clean_answer


# 監聽所有來自 /callback 的 Post Request
@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


# 處理訊息
@handler.add(MessageEvent, message=TextMessage)
# def handle_message(event):
#     msg = event.message.text
#     try:
#         GPT_answer = GPT_response(msg)
#         print(GPT_answer)
#         line_bot_api.reply_message(event.reply_token, TextSendMessage(GPT_answer))
#     except:
#         print(traceback.format_exc())
#         line_bot_api.reply_message(event.reply_token, TextSendMessage('Hungry,I am not connected'))
def handle_message(event):
    
    user_msg = event.message.text
    user_address = "你的預設地址或從使用者獲取"   #根據需求設定 
    mode = 'walking'       # 根據需求設定
    minutes = 15           # 根據需求設定

    try:
        GPT_answer = recommend_food_private(user_address, mode, minutes, event)
        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text="請仿照以下格式輸入：e.g. i want eat taco, in new york USA, 10min drive"),
                TextSendMessage(text=GPT_answer)
            ]
        )
    except Exception as e:
        print(traceback.format_exc())
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text='抱歉，暫時無法提供推薦'))

@handler.add(PostbackEvent)
def handle_message(event):
    print(event.postback.data)


@handler.add(MemberJoinedEvent)
def welcome(event):
    uid = event.joined.members[0].user_id
    gid = event.source.group_id
    profile = line_bot_api.get_group_member_profile(gid, uid)
    name = profile.display_name
    message = TextSendMessage(text=f'{name}歡迎加入')
    line_bot_api.reply_message(event.reply_token, message)
        
        
import os
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

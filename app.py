import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import openai

app = Flask(__name__)

# 環境変数から取得
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 必要な環境変数が設定されているかチェック
if not all([LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, OPENAI_API_KEY]):
    raise ValueError("LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, OPENAI_API_KEY を設定してください。")

# Line Bot と OpenAI のクライアント初期化
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()
    prompt = (
        f"以下の材料で作れるレシピを3つ考えてください:\n"
        f"材料: {user_text}\n"
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたは料理の達人で、かわいくレシピを紹介するガイドです。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.8,
        )
        recipe_text = response.choices[0].message.content.strip()
    except Exception as e:
        recipe_text = "ごめんなさい、レシピの生成中にエラーが発生しちゃった…"

    # LINE に返信
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=recipe_text)
    )

if __name__ == "__main__":
    # ポートは環境変数 PORT or 8000
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

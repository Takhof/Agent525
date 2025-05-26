import os
from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from openai import OpenAI

# .env から環境変数を読み込む
load_dotenv()

# Flask アプリケーション生成
app = Flask(__name__)

# ヘルスチェック用エンドポイント
@app.route("/", methods=["GET"])
def health_check():
    return "OK", 200

# 環境変数から取得
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 必要な環境変数が設定されているかチェック
if not all([LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, OPENAI_API_KEY]):
    raise ValueError("LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, OPENAI_API_KEY を設定してください。")

# LINE Bot API と WebhookHandler を初期化
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# OpenAI v1 クライアントを初期化
client = OpenAI(api_key=OPENAI_API_KEY)

# Webhook 受信用エンドポイント
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    print(f"[DEBUG] Signature: {signature}")
    print(f"[DEBUG] Body: {body}")

    # 簡易テスト用に署名検証をスキップ
    if os.getenv("DISABLE_SIGNATURE_CHECK", "false").lower() == "true":
        handler.handle(body, signature)
        return "OK"

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("[ERROR] Invalid signature. Request aborted.")
        abort(400)
    return "OK"

# メッセージイベントハンドラ
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()
    prompt = (
        f"以下の材料で作れるレシピを3つ考えてください:\n"
        f"材料: {user_text}\n"
        "かわいく説明してね💕"
    )
    try:
        # OpenAI v1 の new interface を使用
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたは料理の達人で、かわいくレシピを紹介するガイドです。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.8,
        )
        # レスポンスからメッセージ抽出
        recipe_text = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] OpenAI API error: {e}")
        recipe_text = "ごめんなさい、レシピの生成中にエラーが発生しちゃった…"

    # LINE に返信
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=recipe_text)
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

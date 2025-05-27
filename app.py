import os
from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, FlexSendMessage
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

# テキストをバブル用にチャンクに分割するヘルパー
def make_bubble_chunks(text, max_chars=2000):
    # テキストを文章単位で分割
    sentences = text.replace("\n", " ").split('。')
    bubbles = []
    current = ''
    for sentence in sentences:
        if not sentence.strip():
            continue
        piece = sentence + '。'
        if current and len(current) + len(piece) > max_chars:
            bubbles.append(current)
            current = piece
        else:
            current += piece
    if current:
        bubbles.append(current)
    return bubbles

# Webhook 受信用エンドポイント
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    if os.getenv("DISABLE_SIGNATURE_CHECK", "false").lower() == "true":
        handler.handle(body, signature)
        return "OK"
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# メッセージイベントハンドラ
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()
    prompt = (
        f"以下の材料で作れるレシピを考えてください。短くまとめてください。でもかわいく、Emoticon適度に使って:\n"
        f"材料: {user_text}"
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたは短くてかわいいレシピを紹介するガイドです。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.8,
        )
        recipe_text = response.choices[0].message.content.strip()
    except Exception:
        recipe_text = "ごめんなさい、レシピの生成中にエラーが発生しちゃった…"

    # バブル用テキストを作成
    bubble_texts = make_bubble_chunks(recipe_text, max_chars=2000)
    bubbles = []
    for text in bubble_texts[:10]:  # 最大10バブル
        bubbles.append({
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": text, "wrap": True}
                ]
            }
        })
    flex = FlexSendMessage(
        alt_text="レシピ",
        contents={"type": "carousel", "contents": bubbles}
    )
    try:
        line_bot_api.reply_message(event.reply_token, flex)
    except LineBotApiError as e:
        print(f"[WARNING] Reply failed: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

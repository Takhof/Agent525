import os
import traceback
from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, FlexSendMessage
from openai import OpenAI
from linebot.models import ImageMessage, TextSendMessage
import tempfile
import base64

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

#画像をBase64エンコーディング
def base64_encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
    

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

def build_recipe_messages(recipe_text, max_chars=5000, max_groups=5, group_size=3):
    return [TextSendMessage(text=recipe_text)]



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


#Detect food from image
def detect_ingredients_from_image(image_path):
    encoded_image = base64_encode_image(image_path)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "あなたは冷蔵庫の中身を見て、食材をリストアップするアシスタントです。"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "この画像の中にある食材をリストアップしてください。一回リストアップしたら終了してください。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"}}
                ]
            }
        ],
        max_tokens=300
    )
    return response.choices[0].message.content.strip()

def generate_recipe_from_ingredients(ingredients):
    prompt = (
        f"以下の材料で作れるレシピを１っこだけ考えてください。短くまとめてください。でもかわいく、Emoticon適度に使って:\n"
        f"材料: {ingredients}"
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたは短くてかわいいレシピを紹介するガイドです。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.8,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "ごめんなさい、レシピの生成中にエラーが発生しちゃった…"



# メッセージイベントハンドラ
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()

    try:
        # ✅ まずはすぐに返信！（reply_tokenは1回しか使えないの！）
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="材料みたよ〜っ🍅✨ いまかわいいレシピつくってるね💕")
        )

        # 🧠 ここでレシピを生成（ちょっと時間かかってもOK）
        prompt = (
            f"以下の材料で作れるレシピを１っこだけ考えてください。"
            f"短くまとめてください。でもかわいく、Emoticon適度に使って:\n"
            f"材料: {user_text}"
        )
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
        messages = build_recipe_messages(recipe_text)

        # 📩 push_message でユーザーにあとから結果を送信！
        user_id = event.source.user_id
        for msg in messages:
            line_bot_api.push_message(user_id, msg)

    except Exception as e:
        print(f"[ERROR] text message error: {e}")
        traceback.print_exc()
        line_bot_api.push_message(
            event.source.user_id,
            TextSendMessage(text="えへへ、レシピの生成でちょっとおっちょこしちゃったの…💦")
        )

#Imageから料理を作るハンドラ
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    # ① すぐレスポンス返して LINE を安心させる（リトライ防止）
    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="れしぴ考え中だよ〜っ📷✨ちょっとまっててね！")
        )
    except LineBotApiError as e:
        print(f"[WARNING] reply_message failed early: {e}")

    # ② あとは別スレッドで処理
    import threading

    def async_job():
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                message_content = line_bot_api.get_message_content(event.message.id)
                for chunk in message_content.iter_content():
                    tmp_file.write(chunk)
                tmp_path = tmp_file.name

            ingredients = detect_ingredients_from_image(tmp_path)
            recipe = generate_recipe_from_ingredients(ingredients)
            messages = build_recipe_messages(recipe)

            for msg in messages:
                line_bot_api.push_message(event.source.user_id, msg)

        except Exception as e:
            print("[ERROR] async_job failed:", e)

    threading.Thread(target=async_job).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

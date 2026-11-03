import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import io
import os
import zipfile
import json
import uuid
import time
from google import genai
from google.genai import types

st.set_page_config(page_title="Ant YOLO Dataset Builder", layout="wide")

st.title("🐜 アリのYOLO学習データ作成ツール (AI下書きアシスト搭載)")
st.write("AIが自動でアリを四角で囲み、人間が手動で微調整（追加・移動・サイズ変更・削除）してYOLOデータを作成します。")

# ---------------------------------------------------------
# データ保存用ディレクトリ
# ---------------------------------------------------------
DATA_DIR = "ant_dataset"
IMAGE_DIR = os.path.join(DATA_DIR, "images", "all")
LABEL_DIR = os.path.join(DATA_DIR, "labels", "all")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(LABEL_DIR, exist_ok=True)

# ---------------------------------------------------------
# サイドバー（APIキー設定）
# ---------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 設定")
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        api_key = st.text_input(
            "Gemini APIキー (AI下書き用)",
            type="password",
            placeholder="AIzaSy...",
            help="AIによる自動下書きを使用するためのAPIキーです。"
        )
    else:
        st.success("👑 APIキー設定済み（Secrets）")

    st.markdown("---")
    model_choice = st.selectbox(
        "AI下書きモデル",
        ["gemini-flash-latest", "gemini-3.8-flash", "gemini-3.1-flash-lite"],
        index=0
    )

# ---------------------------------------------------------
# セッション状態の初期化
# ---------------------------------------------------------
if "current_file_id" not in st.session_state:
    st.session_state.current_file_id = None
if "initial_drawing" not in st.session_state:
    st.session_state.initial_drawing = None
if "canvas_objects" not in st.session_state:
    st.session_state.canvas_objects = []

# ---------------------------------------------------------
# 画像アップロード
# ---------------------------------------------------------
uploaded_file = st.file_uploader(
    "アリの写真を選択してください",
    type=["jpg", "jpeg", "png"]
)

# AIによる自動バウンディングボックス検出関数
def detect_boxes_with_ai(image: Image.Image, api_key: str, model_name: str, display_w: int, display_h: int):
    client = genai.Client(api_key=api_key)
    
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='JPEG', quality=95)
    img_bytes = img_byte_arr.getvalue()
    
    prompt = """
Detect every single ant in this image. 
Return bounding boxes for each ant enclosing its body (head, thorax, and gaster).
Return ONLY a valid JSON list of objects formatted as:
[
  {"box_2d": [ymin, xmin, ymax, xmax], "label": "ant"}
]
ymin, xmin, ymax, xmax must be normalized integers from 0 to 1000.
"""
    contents = [
        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
        prompt
    ]
    config = types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=8192,
        response_mime_type="application/json"
    )

    res = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=config
    )
    
    text = res.text.strip()
    if text.startswith("```json"): text = text[7:]
    if text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    
    boxes = json.loads(text.strip())
    
    # Fabric.js 用の initial_drawing オブジェクト形式に変換
    objects = []
    for item in boxes:
        box = item.get("box_2d", [])
        if len(box) == 4:
            ymin, xmin, ymax, xmax = box
            left = (xmin / 1000.0) * display_w
            top = (ymin / 1000.0) * display_h
            w = ((xmax - xmin) / 1000.0) * display_w
            h = ((ymax - ymin) / 1000.0) * display_h
            
            # 極小サイズの補正
            w = max(10, w)
            h = max(10, h)
            
            objects.append({
                "type": "rect",
                "left": left,
                "top": top,
                "width": w,
                "height": h,
                "fill": "rgba(255, 0, 0, 0.15)",
                "stroke": "#ff0000",
                "strokeWidth": 2,
                "scaleX": 1,
                "scaleY": 1,
                "angle": 0,
                "hasControls": True,
                "hasBorders": True
            })
            
    return {"version": "4.4.0", "objects": objects}

if uploaded_file is not None:
    # 新しい写真がアップされたらリセット
    file_sig = f"{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.current_file_id != file_sig:
        st.session_state.current_file_id = file_sig
        st.session_state.initial_drawing = None
        st.session_state.canvas_objects = []

    image = Image.open(uploaded_file).convert("RGB")

    max_size = 1200
    scale = min(max_size / image.width, max_size / image.height, 1.0)
    display_width = int(image.width * scale)
    display_height = int(image.height * scale)
    display_image = image.resize((display_width, display_height))

    st.caption(f"画像解像度：{image.width} × {image.height}px")

    # ---------------------------------------------------------
    # 🤖 AI自動下書きボタン
    # ---------------------------------------------------------
    col_ai, col_help = st.columns([1, 2])
    with col_ai:
        if st.button("🤖 AIでアリを自動検出（下書き）", type="primary"):
            if not api_key:
                st.error("サイドバーにGemini APIキーを入力してください。")
            else:
                with st.spinner("AIが画像内のアリを自動で四角で囲んでいます..."):
                    try:
                        drawing_data = detect_boxes_with_ai(image, api_key, model_choice, display_width, display_height)
                        st.session_state.initial_drawing = drawing_data
                        st.session_state.canvas_objects = drawing_data.get("objects", [])
                        st.success(f"✨ AIが {len(st.session_state.canvas_objects)} 匹のアリを自動で囲みました！修正・追加してください。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"AI検出中にエラーが発生しました: {e}")
    with col_help:
        st.caption("※ AIが自動で四角形を配置します。四角をクリックして位置移動・サイズ変更・削除（Deleteキー）が可能です。ドラッグで新しい四角も追加できます。")

    st.subheader("アリの枠付け（編集・確認）")

    # キャンバス描画
    canvas_result = st_canvas(
        fill_color="rgba(255, 0, 0, 0.15)",
        stroke_width=2,
        stroke_color="#ff0000",
        background_image=display_image,
        update_streamlit=True,
        height=display_height,
        width=display_width,
        drawing_mode="rect",
        initial_drawing=st.session_state.initial_drawing,
        key=f"canvas_{st.session_state.current_file_id}",
    )

    # キャンバスで編集された最新の四角形データをセッションに保存（消失防止）
    if canvas_result.json_data is not None:
        raw_objs = canvas_result.json_data.get("objects", [])
        st.session_state.canvas_objects = [o for o in raw_objs if o.get("type") == "rect"]

    current_count = len(st.session_state.canvas_objects)
    st.write(f"現在の四角形の数：**{current_count} 匹**")

    # ---------------------------------------------------------
    # 保存処理（セッションデータから確実に書き出し）
    # ---------------------------------------------------------
    if st.button("💾 学習データとして保存", type="secondary"):
        valid_boxes = st.session_state.canvas_objects
        if not valid_boxes:
            st.warning("⚠️ アリが四角形で囲まれていません。")
        else:
            file_id = uuid.uuid4().hex[:12]
            image_name = f"{file_id}.jpg"
            label_name = f"{file_id}.txt"

            image_path = os.path.join(IMAGE_DIR, image_name)
            label_path = os.path.join(LABEL_DIR, label_name)

            # 原寸高解像度画像を保存
            image.save(image_path, quality=95)

            labels = []
            for obj in valid_boxes:
                left = float(obj.get("left", 0))
                top = float(obj.get("top", 0))
                width = float(obj.get("width", 0)) * float(obj.get("scaleX", 1))
                height = float(obj.get("height", 0)) * float(obj.get("scaleY", 1))

                # 中心座標
                center_x = left + width / 2.0
                center_y = top + height / 2.0

                # 0〜1のYOLO正規化座標に変換
                x = center_x / display_width
                y = center_y / display_height
                w = width / display_width
                h = height / display_height

                x = max(0.0, min(1.0, x))
                y = max(0.0, min(1.0, y))
                w = max(0.0, min(1.0, w))
                h = max(0.0, min(1.0, h))

                # クラスID 0 (ant)
                labels.append(f"0 {x:.6f} {y:.6f} {w:.6f} {h:.6f}")

            # ラベルファイル書き出し
            with open(label_path, "w", encoding="utf-8") as f:
                f.write("\n".join(labels))

            st.success(f"🎉 成功！ **{len(labels)} 匹分**の学習データを正常に保存しました！（画像: `{image_name}`）")

    st.divider()
    st.subheader("保存済みデータ一覧")

    saved_images = [
        f for f in os.listdir(IMAGE_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    st.write(f"📁 保存済み写真：**{len(saved_images)} 枚**")

    if saved_images:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for root, dirs, files in os.walk(DATA_DIR):
                for file in files:
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, DATA_DIR)
                    zip_file.write(full_path, arcname)

        st.download_button(
            label="📦 学習データセットを一括ZIPダウンロード",
            data=zip_buffer.getvalue(),
            file_name="ant_yolo_dataset.zip",
            mime="application/zip"
        )

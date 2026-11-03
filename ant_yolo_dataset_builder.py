import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import os
import io
import zipfile
import hashlib
from datetime import datetime

st.set_page_config(page_title="Ant YOLO Dataset Builder", layout="wide")

st.title("🐜 Ant YOLO Dataset Builder（自作AIアシスト搭載）")

# 保存先ディレクトリの準備
DATA_DIR = "ant_dataset"
IMAGES_DIR = os.path.join(DATA_DIR, "images", "all")
LABELS_DIR = os.path.join(DATA_DIR, "labels", "all")
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(LABELS_DIR, exist_ok=True)

# セッション状態の初期化
if "canvas_key" not in st.session_state:
    st.session_state["canvas_key"] = 0
if "persistent_boxes" not in st.session_state:
    st.session_state["persistent_boxes"] = []
if "last_image_hash" not in st.session_state:
    st.session_state["last_image_hash"] = None

# --- YOLOモデルの診断とロード ---
yolo_diag = []
model = None
YOLO_AVAILABLE = False

try:
    from ultralytics import YOLO
    yolo_diag.append("✅ ultralytics ライブラリ: OK")
except Exception as e:
    yolo_diag.append(f"❌ ultralytics エラー: {e}")

# パスの探索
possible_paths = [
    "best.pt",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "best.pt"),
    "manual_best.pt"
]
found_path = None
for p in possible_paths:
    if os.path.exists(p):
        found_path = p
        break

if found_path and "YOLO" in locals():
    try:
        model = YOLO(found_path)
        YOLO_AVAILABLE = True
        yolo_diag.append(f"✅ モデル読み込み成功！ ({os.path.basename(found_path)})")
    except Exception as e:
        yolo_diag.append(f"❌ モデル読込エラー: {e}")
elif not found_path:
    yolo_diag.append("⚠️ best.pt が見つかりません")

# サイドバー表示
with st.sidebar:
    st.subheader("🤖 AIアシスト状態")
    for msg in yolo_diag:
        if "✅" in msg:
            st.success(msg)
        elif "❌" in msg:
            st.error(msg)
        else:
            st.warning(msg)

    # 画面から直接 best.pt を読み込むフォールバック
    if not YOLO_AVAILABLE and "YOLO" in locals():
        st.markdown("---")
        st.write("📁 **PCの `best.pt` を直接ドラッグ＆ドロップ：**")
        uploaded_pt = st.file_uploader("best.pt を選択", type=["pt"], key="pt_uploader")
        if uploaded_pt is not None:
            try:
                with open("manual_best.pt", "wb") as f:
                    f.write(uploaded_pt.getbuffer())
                model = YOLO("manual_best.pt")
                YOLO_AVAILABLE = True
                st.success("🎉 モデル読み込み完了！")
                st.rerun()
            except Exception as e:
                st.error(f"読み込み失敗: {e}")

    if YOLO_AVAILABLE:
        conf_thresh = st.slider("検出の感度 (Confidence)", 0.1, 0.9, 0.25, 0.05,
                                help="数値を下げると見逃しが減り、上げると誤検知が減ります")

uploaded_file = st.file_uploader("写真をアップロードしてください（8枚目以降の写真をどうぞ！）", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    current_image_hash = hashlib.sha256(file_bytes).hexdigest()

    if st.session_state["last_image_hash"] != current_image_hash:
        st.session_state["last_image_hash"] = current_image_hash
        st.session_state["persistent_boxes"] = []
        st.session_state["canvas_key"] += 1

    image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    orig_w, orig_h = image.size

    canvas_width = 900
    scale = canvas_width / orig_w
    canvas_height = int(orig_h * scale)

    # --- AI自動下書きボタン ---
    if YOLO_AVAILABLE and model is not None:
        col_ai, col_clear = st.columns([2, 1])
        with col_ai:
            if st.button("🤖 自作AIで自動下書き（0.1秒でアリを囲む）", type="primary", use_container_width=True):
                with st.spinner("自作AI（Ant-YOLO）がアリを探しています..."):
                    results = model.predict(image, imgsz=640, conf=conf_thresh, verbose=False)
                    boxes = results[0].boxes
                    ai_objects = []
                    for b in boxes:
                        x1, y1, x2, y2 = b.xyxy[0].tolist()
                        ai_objects.append({
                            "type": "rect",
                            "version": "4.4.0",
                            "originX": "left",
                            "originY": "top",
                            "left": round(x1 * scale, 1),
                            "top": round(y1 * scale, 1),
                            "width": round((x2 - x1) * scale, 1),
                            "height": round((y2 - y1) * scale, 1),
                            "fill": "rgba(255, 0, 0, 0.2)",
                            "stroke": "red",
                            "strokeWidth": 2,
                            "strokeUniform": True,
                            "angle": 0
                        })
                    st.session_state["persistent_boxes"] = ai_objects
                    st.session_state["canvas_key"] += 1
                    st.rerun()

        with col_clear:
            if st.button("🗑️ 四角をすべてクリア", use_container_width=True):
                st.session_state["persistent_boxes"] = []
                st.session_state["canvas_key"] += 1
                st.rerun()

    st.caption("💡 操作方法: AIが描いた四角を確認し、見逃されたアリを手動でドラッグして四角を追加してください。")

    initial_drawing = {
        "version": "4.4.0",
        "objects": st.session_state["persistent_boxes"]
    }

    canvas_result = st_canvas(
        fill_color="rgba(255, 0, 0, 0.2)",
        stroke_width=2,
        stroke_color="red",
        background_image=image.resize((canvas_width, canvas_height)),
        update_streamlit=True,
        height=canvas_height,
        width=canvas_width,
        drawing_mode="rect",
        initial_drawing=initial_drawing,
        key=f"canvas_{st.session_state['canvas_key']}",
    )

    if canvas_result.json_data is not None and "objects" in canvas_result.json_data:
        st.session_state["persistent_boxes"] = canvas_result.json_data["objects"]

    ant_boxes = [obj for obj in st.session_state["persistent_boxes"] if obj.get("type") == "rect"]
    count = len(ant_boxes)

    st.subheader(f"囲んだアリの数: **{count} 匹**")

    if st.button("💾 この内容で学習データを保存する", type="primary"):
        if count == 0:
            st.error("四角で囲まれたアリが0匹です。")
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"ant_{timestamp}"

            img_save_path = os.path.join(IMAGES_DIR, f"{base_filename}.jpg")
            image.save(img_save_path, "JPEG", quality=95)

            label_save_path = os.path.join(LABELS_DIR, f"{base_filename}.txt")
            with open(label_save_path, "w") as f:
                for obj in ant_boxes:
                    l = obj["left"]
                    t = obj["top"]
                    w = obj["width"]
                    h = obj["height"]

                    center_x = (l + w / 2) / scale / orig_w
                    center_y = (t + h / 2) / scale / orig_h
                    norm_w = w / scale / orig_w
                    norm_h = h / scale / orig_h

                    f.write(f"0 {center_x:.6f} {center_y:.6f} {norm_w:.6f} {norm_h:.6f}\n")

            st.success(f"🎉 {count}匹のアリの学習データを保存しました！")
            st.session_state["persistent_boxes"] = []
            st.session_state["canvas_key"] += 1
            st.rerun()

st.divider()

saved_images = sorted([f for f in os.listdir(IMAGES_DIR) if f.endswith(".jpg")])
st.subheader(f"📁 保存済みデータ（現在: {len(saved_images)} 枚）")

if saved_images:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(DATA_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, DATA_DIR)
                zip_file.write(file_path, arcname)

    st.download_button(
        label="📦 学習データセット（ZIP）をダウンロード",
        data=zip_buffer.getvalue(),
        file_name="ant_yolo_dataset.zip",
        mime="application/zip",
    )

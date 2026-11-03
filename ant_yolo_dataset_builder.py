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

DATA_DIR = "ant_dataset"
IMAGES_DIR = os.path.join(DATA_DIR, "images", "all")
LABELS_DIR = os.path.join(DATA_DIR, "labels", "all")
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(LABELS_DIR, exist_ok=True)

if "canvas_key" not in st.session_state:
    st.session_state["canvas_key"] = 0
if "persistent_boxes" not in st.session_state:
    st.session_state["persistent_boxes"] = []
if "last_image_hash" not in st.session_state:
    st.session_state["last_image_hash"] = None

# --- YOLOモデルのロード ---
model = None
YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    if os.path.exists("best.pt"):
        model = YOLO("best.pt")
        YOLO_AVAILABLE = True
except Exception as e:
    YOLO_AVAILABLE = False

with st.sidebar:
    st.subheader("🤖 AIアシスト状態")
    if YOLO_AVAILABLE:
        st.success("✅ 自作AIモデル（Ant-YOLO v1）稼働中！")
        conf_thresh = st.slider("検出の感度 (Confidence)", 0.1, 0.9, 0.40, 0.05,
                                help="数値を上げると誤検知（大きな枠やゴミ）が減ります")
        max_box_size = st.slider("アリの最大サイズ制限 (%)", 5, 30, 12, 1,
                                 help="これより大きい四角はアリではないとして除外します")
    else:
        st.warning("⚠️ best.pt 読み込み待機中")

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

    if YOLO_AVAILABLE and model is not None:
        col_ai, col_clear = st.columns([2, 1])
        with col_ai:
            if st.button("🤖 自作AIで自動下書き（0.1秒でアリを囲む）", type="primary", use_container_width=True):
                with st.spinner("自作AIが適切なサイズのアリを探しています..."):
                    results = model.predict(image, imgsz=640, conf=conf_thresh, iou=0.45, verbose=False)
                    boxes = results[0].boxes
                    ai_objects = []
                    
                    # 画面幅に対する最大許容ピクセル
                    max_allowed_w = orig_w * (max_box_size / 100.0)
                    max_allowed_h = orig_h * (max_box_size / 100.0)

                    for b in boxes:
                        x1, y1, x2, y2 = b.xyxy[0].tolist()
                        box_w = x2 - x1
                        box_h = y2 - y1

                        # 大きすぎる枠（部屋全体や水滴の誤認識）を除外！
                        if box_w > max_allowed_w or box_h > max_allowed_h:
                            continue

                        ai_objects.append({
                            "type": "rect",
                            "version": "4.4.0",
                            "originX": "left",
                            "originY": "top",
                            "left": round(x1 * scale, 1),
                            "top": round(y1 * scale, 1),
                            "width": round(box_w * scale, 1),
                            "height": round(box_h * scale, 1),
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

    st.caption("💡 操作方法: 四角をクリックしてキーボードの「Delete」または「Backspace」で消去、ドラッグで追加できます。")

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

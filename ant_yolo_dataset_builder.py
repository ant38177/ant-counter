import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import io
import os
import zipfile
import uuid
import hashlib

st.set_page_config(
    page_title="Ant YOLO Dataset Builder",
    layout="wide"
)

st.title("🐜 アリのYOLO学習データ作成ツール")
st.write(
    "写真に写っているアリを四角形で囲み、"
    "YOLO形式の学習データを作成します。"
)

# ---------------------------------------------------------
# データ保存用ディレクトリ
# ---------------------------------------------------------
DATA_DIR = "ant_dataset"
IMAGE_DIR = os.path.join(DATA_DIR, "images", "all")
LABEL_DIR = os.path.join(DATA_DIR, "labels", "all")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(LABEL_DIR, exist_ok=True)

# ---------------------------------------------------------
# セッション初期化
# ---------------------------------------------------------
if "current_image_hash" not in st.session_state:
    st.session_state["current_image_hash"] = None

if "persistent_boxes" not in st.session_state:
    st.session_state["persistent_boxes"] = []

if "canvas_key" not in st.session_state:
    st.session_state["canvas_key"] = 0

# ---------------------------------------------------------
# 画像アップロード
# ---------------------------------------------------------
uploaded_file = st.file_uploader(
    "アリの写真を選択してください",
    type=["jpg", "jpeg", "png"],
    key="ant_image_uploader"
)

if uploaded_file is not None:

    image_bytes = uploaded_file.getvalue()
    image_hash = hashlib.sha256(image_bytes).hexdigest()

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    orig_w, orig_h = image.size

    # 写真が切り替わった場合はリセット
    if image_hash != st.session_state["current_image_hash"]:
        st.session_state["current_image_hash"] = image_hash
        st.session_state["persistent_boxes"] = []
        st.session_state["canvas_key"] += 1

    max_disp_w = 1100
    scale = min(max_disp_w / orig_w, 1.0)
    disp_w = max(1, int(orig_w * scale))
    disp_h = max(1, int(orig_h * scale))

    disp_img = image.resize((disp_w, disp_h))

    st.caption(
        f"原寸：{orig_w} × {orig_h}px ｜ "
        f"表示：{disp_w} × {disp_h}px"
    )

    st.subheader("アリを四角形で囲んでください")

    canvas_result = st_canvas(
        fill_color="rgba(255, 0, 0, 0.2)",
        stroke_width=2,
        stroke_color="#ff0000",
        background_image=disp_img,
        update_streamlit=True,
        height=disp_h,
        width=disp_w,
        drawing_mode="rect",
        key=f"ant_canvas_{st.session_state['canvas_key']}"
    )

    if canvas_result.json_data is not None:
        raw_objects = canvas_result.json_data.get("objects", [])
        rect_objects = [
            obj for obj in raw_objects
            if str(obj.get("type", "")).lower() == "rect"
        ]
        st.session_state["persistent_boxes"] = rect_objects

    current_boxes = st.session_state["persistent_boxes"]
    count = len(current_boxes)

    st.metric(
        label="囲んだアリの数",
        value=f"{count} 匹"
    )

    # -----------------------------------------------------
    # 学習データ保存
    # -----------------------------------------------------
    if st.button("💾 この内容で学習データを保存する", type="primary"):
        if count == 0:
            st.warning("アリを四角形で囲んでください。")
        else:
            file_id = uuid.uuid4().hex[:12]
            image_name = f"{file_id}.jpg"
            label_name = f"{file_id}.txt"

            image_path = os.path.join(IMAGE_DIR, image_name)
            label_path = os.path.join(LABEL_DIR, label_name)

            image.save(image_path, format="JPEG", quality=95)

            labels = []
            for obj in current_boxes:
                left = float(obj.get("left", 0))
                top = float(obj.get("top", 0))
                width = float(obj.get("width", 0)) * float(obj.get("scaleX", 1))
                height = float(obj.get("height", 0)) * float(obj.get("scaleY", 1))

                center_x = left + width / 2.0
                center_y = top + height / 2.0

                norm_x = center_x / disp_w
                norm_y = center_y / disp_h
                norm_w = width / disp_w
                norm_h = height / disp_h

                norm_x = max(0.0, min(1.0, norm_x))
                norm_y = max(0.0, min(1.0, norm_y))
                norm_w = max(0.0, min(1.0, norm_w))
                norm_h = max(0.0, min(1.0, norm_h))

                labels.append(f"0 {norm_x:.6f} {norm_y:.6f} {norm_w:.6f} {norm_h:.6f}")

            with open(label_path, "w", encoding="utf-8") as f:
                f.write("\n".join(labels))

            st.balloons()
            st.success(f"{len(labels)}匹分の学習データを保存しました。（`{image_name}`）")

            st.session_state["persistent_boxes"] = []
            st.session_state["canvas_key"] += 1
            st.rerun()

# ---------------------------------------------------------
# 保存済みデータ管理（💡 選択して削除機能を追加）
# ---------------------------------------------------------
st.divider()
st.subheader("📁 保存済みデータ管理")

saved_images = [
    f for f in os.listdir(IMAGE_DIR)
    if f.lower().endswith((".jpg", ".jpeg", ".png"))
]

st.write(f"保存済み写真数：**{len(saved_images)} 枚**")

if saved_images:
    col_del, col_down = st.columns([1, 1])

    # 🗑️ 個別選択して削除
    with col_del:
        st.write("##### 🗑️ 写真を選んで削除")
        target_file = st.selectbox("削除したい写真を選択", saved_images)
        
        if target_file:
            target_img_path = os.path.join(IMAGE_DIR, target_file)
            base_id = os.path.splitext(target_file)[0]
            target_lbl_path = os.path.join(LABEL_DIR, f"{base_id}.txt")

            # プレビュー表示で消す写真を確認
            st.image(target_img_path, width=220, caption=f"選択中: {target_file}")

            if st.button(f"🗑️ `{target_file}` を削除する", type="secondary"):
                if os.path.exists(target_img_path):
                    os.remove(target_img_path)
                if os.path.exists(target_lbl_path):
                    os.remove(target_lbl_path)
                st.success(f"写真 `{target_file}` と学習ラベルを削除しました。")
                st.rerun()

    # 📦 一括ダウンロード
    with col_down:
        st.write("##### 📦 データセット一括ダウンロード")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for root, dirs, files in os.walk(DATA_DIR):
                for file in files:
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, DATA_DIR)
                    zip_file.write(full_path, arcname)

        st.download_button(
            label="📦 学習データセット（ZIP）をダウンロード",
            data=zip_buffer.getvalue(),
            file_name="ant_yolo_dataset.zip",
            mime="application/zip",
            use_container_width=True
        )

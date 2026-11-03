import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import io
import os
import zipfile
import json
import uuid

st.set_page_config(page_title="Ant YOLO Dataset Builder", layout="wide")

st.title("🐜 アリのYOLO学習データ作成ツール")
st.write("写真に写っているアリを四角形で囲み、YOLO形式の学習データを作成します。")

DATA_DIR = "ant_dataset"
IMAGE_DIR = os.path.join(DATA_DIR, "images", "all")
LABEL_DIR = os.path.join(DATA_DIR, "labels", "all")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(LABEL_DIR, exist_ok=True)

uploaded_file = st.file_uploader(
    "アリの写真を選択してください",
    type=["jpg", "jpeg", "png"]
)

if uploaded_file is not None:
    image = Image.open(uploaded_file).convert("RGB")

    max_size = 1200
    scale = min(max_size / image.width, max_size / image.height, 1.0)

    display_width = int(image.width * scale)
    display_height = int(image.height * scale)

    display_image = image.resize((display_width, display_height))

    st.write(f"画像サイズ：{image.width} × {image.height}")

    st.subheader("アリを四角形で囲んでください")

    canvas_result = st_canvas(
        fill_color="rgba(255, 0, 0, 0.15)",
        stroke_width=2,
        stroke_color="#ff0000",
        background_image=display_image,
        update_streamlit=True,
        height=display_height,
        width=display_width,
        drawing_mode="rect",
        key="ant_canvas"
    )

    objects = []
    if canvas_result.json_data is not None:
        objects = canvas_result.json_data.get("objects", [])

    st.write(f"囲んだアリの数：{len(objects)}")

    if st.button("学習データとして保存"):
        if not objects:
            st.warning("アリを四角形で囲んでください。")
        else:
            file_id = uuid.uuid4().hex[:12]

            image_name = f"{file_id}.jpg"
            label_name = f"{file_id}.txt"

            image_path = os.path.join(IMAGE_DIR, image_name)
            label_path = os.path.join(LABEL_DIR, label_name)

            image.save(image_path, quality=95)

            labels = []

            for obj in objects:
                if obj.get("type") != "rect":
                    continue

                left = float(obj.get("left", 0))
                top = float(obj.get("top", 0))
                width = float(obj.get("width", 0)) * float(obj.get("scaleX", 1))
                height = float(obj.get("height", 0)) * float(obj.get("scaleY", 1))

                center_x = left + width / 2
                center_y = top + height / 2

                x = center_x / display_width
                y = center_y / display_height
                w = width / display_width
                h = height / display_height

                x = max(0.0, min(1.0, x))
                y = max(0.0, min(1.0, y))
                w = max(0.0, min(1.0, w))
                h = max(0.0, min(1.0, h))

                labels.append(f"0 {x:.6f} {y:.6f} {w:.6f} {h:.6f}")

            with open(label_path, "w", encoding="utf-8") as f:
                f.write("\n".join(labels))

            st.success(f"{len(labels)}匹分の学習データを保存しました。")

    st.divider()
    st.subheader("保存済みデータ")

    saved_images = [
        f for f in os.listdir(IMAGE_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    st.write(f"保存済み写真：{len(saved_images)}枚")

    if st.button("学習データをZIPでダウンロード"):
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for root, dirs, files in os.walk(DATA_DIR):
                for file in files:
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, DATA_DIR)
                    zip_file.write(full_path, arcname)

        st.download_button(
            label="ZIPファイルをダウンロード",
            data=zip_buffer.getvalue(),
            file_name="ant_dataset.zip",
            mime="application/zip"
        )

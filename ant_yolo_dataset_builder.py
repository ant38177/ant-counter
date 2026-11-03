import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import io
import os
import zipfile
import uuid

st.set_page_config(page_title="Ant YOLO Dataset Builder", layout="wide")

st.title("🐜 アリのYOLO学習データ作成ツール (確実保存版)")
st.write("写真に写っているアリを四角形で囲み、YOLO形式の学習データを作成します。")

# ---------------------------------------------------------
# データ保存用ディレクトリ
# ---------------------------------------------------------
DATA_DIR = "ant_dataset"
IMAGE_DIR = os.path.join(DATA_DIR, "images", "all")
LABEL_DIR = os.path.join(DATA_DIR, "labels", "all")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(LABEL_DIR, exist_ok=True)

# ---------------------------------------------------------
# 画像アップロード
# ---------------------------------------------------------
uploaded_file = st.file_uploader(
    "アリの写真を選択してください",
    type=["jpg", "jpeg", "png"]
)

if uploaded_file is not None:
    # 画像の読み込み
    image = Image.open(uploaded_file).convert("RGB")
    orig_w, orig_h = image.size

    # 画面表示用のリサイズ（アスペクト比維持・最大幅1100pxで高精細表示）
    max_disp_w = 1100
    scale = min(max_disp_w / orig_w, 1.0)
    disp_w = int(orig_w * scale)
    disp_h = int(orig_h * scale)
    disp_img = image.resize((disp_w, disp_h))

    st.caption(f"解像度: 原寸 {orig_w} × {orig_h}px ｜ 表示幅 {disp_w}px")
    st.subheader("アリを四角形で囲んでください")

    # 💡 安定したキャンバス（キーを固定し、状態リセットを防ぐ）
    canvas_result = st_canvas(
        fill_color="rgba(255, 0, 0, 0.2)",
        stroke_width=2,
        stroke_color="#ff0000",
        background_image=disp_img,
        update_streamlit=True,
        height=disp_h,
        width=disp_w,
        drawing_mode="rect",
        key="ant_canvas_stable",
    )

    # リアルタイムで四角形を取得
    detected_boxes = []
    if canvas_result.json_data is not None:
        raw_objects = canvas_result.json_data.get("objects", [])
        for obj in raw_objects:
            if obj.get("type") == "rect":
                detected_boxes.append(obj)

    count = len(detected_boxes)
    st.metric(label="現在囲んでいるアリの数", value=f"{count} 匹")

    # ---------------------------------------------------------
    # 💾 保存処理（detected_boxes を直接利用）
    # ---------------------------------------------------------
    if st.button("💾 この内容で学習データを保存する", type="primary"):
        if count == 0:
            st.error("⚠️ 四角形が検出されていません。画像上のアリを四角で囲んでから押してください。")
        else:
            file_id = uuid.uuid4().hex[:12]
            image_name = f"{file_id}.jpg"
            label_name = f"{file_id}.txt"

            image_path = os.path.join(IMAGE_DIR, image_name)
            label_path = os.path.join(LABEL_DIR, label_name)

            # 原寸高解像度画像をそのまま保存
            image.save(image_path, quality=95)

            labels = []
            for obj in detected_boxes:
                left = float(obj.get("left", 0))
                top = float(obj.get("top", 0))
                w = float(obj.get("width", 0)) * float(obj.get("scaleX", 1))
                h = float(obj.get("height", 0)) * float(obj.get("scaleY", 1))

                # 中心座標
                center_x = left + w / 2.0
                center_y = top + h / 2.0

                # YOLO正規化座標（0.0 〜 1.0）
                norm_x = center_x / disp_w
                norm_y = center_y / disp_h
                norm_w = w / disp_w
                norm_h = h / disp_h

                norm_x = max(0.0, min(1.0, norm_x))
                norm_y = max(0.0, min(1.0, norm_y))
                norm_w = max(0.0, min(1.0, norm_w))
                norm_h = max(0.0, min(1.0, norm_h))

                # class 0 (ant)
                labels.append(f"0 {norm_x:.6f} {norm_y:.6f} {norm_w:.6f} {norm_h:.6f}")

            # ラベルファイル書き出し
            with open(label_path, "w", encoding="utf-8") as f:
                f.write("\n".join(labels))

            st.balloons()
            st.success(f"🎉 大成功！ **{len(labels)} 匹分**のアリを学習データとして保存しました！（ファイル名: `{image_name}`）")

    # ---------------------------------------------------------
    # 保存済みデータの一覧 & ZIPダウンロード
    # ---------------------------------------------------------
    st.divider()
    st.subheader("保存済みデータ")

    saved_images = [
        f for f in os.listdir(IMAGE_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    st.write(f"📁 保存済み写真数：**{len(saved_images)} 枚**")

    if saved_images:
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
            mime="application/zip"
        )

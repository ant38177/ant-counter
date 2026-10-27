import cv2
import numpy as np
import streamlit as st
from PIL import Image

st.set_page_config(
    page_title="Ant Worker Counter", page_icon="🐜", layout="wide"
)

st.title("🐜 アリのワーカー数 自動計測＆推計ツール")
st.markdown("写真からアリのワーカー数を正確に検出し、集計します。")

# サイドバーによる感度・フィルター調整
st.sidebar.header("検出感度・フィルター調整")
min_area = st.sidebar.slider(
    "最小サイズ (ゴミ除外)", 10, 500, 80, help="小さすぎるゴミや汚れを除外します"
)
max_area = st.sidebar.slider(
    "最大サイズ (塊除外)",
    500,
    30000,
    8000,
    help="重なり合った巨大な塊を除外します",
)
blur_val = st.sidebar.slider(
    "ノイズ除去強度 (奇数)",
    1,
    15,
    5,
    step=2,
    help="写真のざらつきを抑えます",
)

uploaded_files = st.file_uploader(
    "アリの巣・ケースの写真をアップロード (複数可)",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

if uploaded_files:
  total_counts = []

  for uploaded_file in uploaded_files:
    # 画像の読み込み
    image = Image.open(uploaded_file)
    img_np = np.array(image)
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    # 1. グレースケール変換
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # 2. ガウシアンブラーでノイズ軽減
    if blur_val > 0:
      gray = cv2.GaussianBlur(gray, (blur_val, blur_val), 0)

    # 3. 白背景に対して「黒いアリ」を抽出する二値化 (Otsuの二値化 + 反転)
    _, thresh = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    # 4. モルフォロジー演算で細かいトゲやゴミを消去
    kernel = np.ones((2, 2), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    # 5. 輪郭検出
    contours, _ = cv2.findContours(
        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    valid_contours = []
    for cnt in contours:
      area = cv2.contourArea(cnt)
      # 面積フィルター
      if min_area <= area <= max_area:
        # アスペクト比（極端に細長いゴミなどを除外）
        x, y, w, h = cv2.boundingRect(cnt)
        aspect_ratio = float(w) / h if h > 0 else 0
        if 0.15 <= aspect_ratio <= 6.0:
          valid_contours.append(cnt)

    # 検出結果の描画
    output_img = img_bgr.copy()
    cv2.drawContours(output_img, valid_contours, -1, (0, 255, 0), 2)
    output_rgb = cv2.cvtColor(output_img, cv2.COLOR_BGR2RGB)

    count = len(valid_contours)
    total_counts.append(count)

    st.subheader(f"📁 {uploaded_file.name} (検出ワーカー数: {count} 匹)")
    st.image(output_rgb, use_container_width=True)

  if total_counts:
    st.markdown("---")
    st.metric(
        "検出トータルワーカー数 (平均)", f"{int(np.mean(total_counts))} 匹"
    )

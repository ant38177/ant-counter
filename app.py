import streamlit as st
import cv2
import numpy as np

st.set_page_config(page_title="アリのワーカー数 カウンター", page_icon="🐜", layout="wide")

st.title("🐜 アリのワーカー数 自動計測＆推計ツール")
st.write("写真を1枚〜複数枚アップロードするだけで、画像内のワーカー数を自動カウントし、コロニー全体のトータル数を推計します。")

uploaded_files = st.file_uploader(
    "アリの巣・ケースの写真をアップロードしてください（複数選択可）", 
    type=["jpg", "jpeg", "png"], 
    accept_multiple_files=True
)

if uploaded_files:
    st.sidebar.header("⚙️ 検出感度調整")
    min_area = st.sidebar.slider("最小サイズ（ゴミ除去）", 10, 200, 50)
    max_area = st.sidebar.slider("最大サイズ（固まり除外）", 500, 10000, 5000)

    counts = []
    processed_images = []

    for uploaded_file in uploaded_files:
        file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        count = 0
        output_img = img.copy()
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if min_area < area < max_area:
                count += 1
                cv2.drawContours(output_img, [cnt], -1, (0, 255, 0), 2)
        
        counts.append(count)
        processed_images.append((uploaded_file.name, cv2.cvtColor(output_img, cv2.COLOR_BGR2RGB), count))

    st.markdown("---")
    st.subheader("📊 カウント＆トータル推計結果")

    num_files = len(counts)

    if num_files == 1:
        st.metric(label="🎯 検出トータルワーカー数", value=f"{counts[0]} 匹")
    else:
        max_val = max(counts)
        avg_val = sum(counts) / num_files
        std_dev = np.std(counts)
        estimated_total = int(max_val + (std_dev * 0.5))

        col1, col2, col3 = st.columns(3)
        col1.metric("🔝 最大アングル値 (Max)", f"{max_val} 匹")
        col2.metric("📐 平均値 (Average)", f"{avg_val:.1f} 匹")
        col3.metric("🔮 重複・死角補正推計", f"{estimated_total} 匹")

    st.markdown("---")
    st.subheader("🖼️ 各画像のアナライズ詳細")
    
    cols = st.columns(min(num_files, 3))
    for idx, (name, rgb_img, c) in enumerate(processed_images):
        with cols[idx % 3]:
            st.image(rgb_img, caption=f"{name} (検出: {c}匹)", use_container_width=True)

import io
import json
import re
import time
from PIL import Image, ImageDraw
import streamlit as st
from streamlit_drawable_canvas import st_canvas
from google import genai
from google.genai import types
from google.genai.errors import APIError

# --- ページ設定 ---
st.set_page_config(
    page_title="Ant Worker Counter (高精度・モデル選択版)",
    page_icon="🐜",
    layout="centered"
)

st.title("🐜 Ant Worker Counter")
st.write("【高精度システム維持】1600pxフル解像度 × 田の字4分割ズーム × モデル切替対応！")

# --- 🔒 安全なAPIキー認証システム ---
secrets_key = st.secrets.get("GEMINI_API_KEY", "")
is_admin = st.query_params.get("admin") == "ant"

st.sidebar.header("⚙️ 設定")

if is_admin and secrets_key:
    api_key = secrets_key
    st.sidebar.success("👑 管理者モード（認証済み）")
else:
    api_key = st.sidebar.text_input(
        "Gemini APIキー (無料)",
        value="",
        type="password",
        help="Google AI Studioで取得できる無料キーを入力してください。"
    )
    if not api_key:
        st.sidebar.markdown(
            "[👉 無料のGemini APIキーを取得する (Google AI Studio)](https://aistudio.google.com/app/apikey)"
        )

# 💡 【高精度を維持したまま、いつでも自由にモデルを切り替え可能！】
model_options = {
    "gemini-3.1-flash-lite（🚀 超高速・無料枠制限なし）": "gemini-3.1-flash-lite",
    "gemini-flash-latest（🌟 標準・安定・高精度）": "gemini-flash-latest",
    "gemini-3.8-flash（🎯 最新知能・超高精度 ※混雑時待機あり）": "gemini-3.8-flash",
}

selected_label = st.sidebar.selectbox(
    "AIモデルを選択",
    list(model_options.keys()),
    index=0  # デフォルトは制限に強い flash-lite
)
MODEL_NAME = model_options[selected_label]

st.sidebar.caption(f"現在の選択: `{MODEL_NAME}`")

# --- 画像アップローダー ---
uploaded_file = st.file_uploader(
    "アリのケース・巣の写真を選択",
    type=["jpg", "jpeg", "png"],
)

if uploaded_file:
    if not api_key:
        st.error("⚠️ APIキーが設定されていません。サイドバーにGemini APIキーを入力してください。")
    else:
        orig_image = Image.open(uploaded_file)
        st.image(orig_image, caption="アップロードされた画像", use_container_width=True)

        if st.button("🎯 高精度スキャンを実行する", type="primary"):
            start_time = time.time()
            client = genai.Client(api_key=api_key)

            orig_w, orig_h = orig_image.size

            # 💡 1600px基準で細部を極限まで保持
            max_size = 1600
            proc_img = orig_image.copy()
            if max(orig_w, orig_h) > max_size:
                proc_img.thumbnail((max_size, max_size))

            cur_w, cur_h = proc_img.size

            # 💡 田の字4分割（8%ののりしろ付きで境目のアリも逃さない）
            split_x = int(cur_w * 0.5)
            split_y = int(cur_h * 0.5)
            overlap_x = int(cur_w * 0.08)
            overlap_y = int(cur_h * 0.08)

            quadrants = [
                {
                    "name": "左上の部屋",
                    "box": (0, 0, split_x + overlap_x, split_y + overlap_y),
                },
                {
                    "name": "右上の部屋",
                    "box": (split_x - overlap_x, 0, cur_w, split_y + overlap_y),
                },
                {
                    "name": "左下の部屋",
                    "box": (0, split_y - overlap_y, split_x + overlap_x, cur_h),
                },
                {
                    "name": "右下の部屋",
                    "box": (split_x - overlap_x, split_y - overlap_y, cur_w, cur_h),
                },
            ]

            status_box = st.empty()
            ants_coords = []
            api_start_time = time.time()

            try:
                for idx, quad in enumerate(quadrants):
                    crop_x0, crop_y0, crop_x1, crop_y1 = quad["box"]
                    crop_w = crop_x1 - crop_x0
                    crop_h = crop_y1 - crop_y0

                    cropped_img = proc_img.crop((crop_x0, crop_y0, crop_x1, crop_y1))

                    img_buf = io.BytesIO()
                    cropped_img.save(img_buf, format="JPEG", quality=95)
                    img_bytes = img_buf.getvalue()

                    prompt = (
                        f"You are a world-class myrmecologist analyzing a zoomed-in section ({quad['name']}) of an ant nest.\n"
                        "MISSION: Detect EVERY SINGLE adult ant with 100% precision.\n"
                        "CRITICAL RULES:\n"
                        "1. DENSE CLUSTERS: When ants are touching, overlapping, or exchanging food, DO NOT merge them! Place a separate coordinate for EACH distinct thorax.\n"
                        "2. TYPES: Include swollen amber repletes, regular dark workers, and majors/minors.\n"
                        "3. QUEEN: Identify the queen ant distinctly as 'q'. Regular ants are 'w'.\n"
                        "4. SHADOWS: Look closely along dark acrylic walls, corners, and under larger repletes.\n"
                        "5. EXCLUSIONS: Do NOT count brood (eggs, larvae, white/cream pupae/cocoons) or cotton/screws.\n"
                        "6. Format: coordinates x and y integers 0 to 1000. Output ONLY raw 2D array: [[x,y,'w'],[x,y,'q']]. No markdown."
                    )

                    # 💡 503混雑や429制限を自動で通り抜ける再試行ガード
                    resp = None
                    for attempt in range(3):
                        try:
                            status_box.info(f"🔍 [{idx+1}/4] {quad['name']} を高精度スキャン中... (モデル: {MODEL_NAME})")
                            resp = client.models.generate_content(
                                model=MODEL_NAME,
                                contents=[
                                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                                    prompt
                                ],
                                config=types.GenerateContentConfig(
                                    response_mime_type="application/json",
                                    max_output_tokens=2000,
                                )
                            )
                            break
                        except Exception as e:
                            err_str = str(e)
                            if "503" in err_str or "UNAVAILABLE" in err_str:
                                if attempt < 2:
                                    status_box.warning(f"⚠️ Googleサーバーが一時混雑しています。3秒後に自動再開します（{attempt+1}/3）...")
                                    time.sleep(3.0)
                                else:
                                    raise e
                            elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                                if attempt < 2:
                                    status_box.warning(f"⚠️ 無料枠の制限を検知。安全のため12秒待機して再開します（{attempt+1}/3）...")
                                    time.sleep(12.0)
                                else:
                                    raise e
                            else:
                                raise e

                    res_text = resp.text.strip() if resp and resp.text else "[]"
                    res_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", res_text)

                    # パース処理
                    raw_items = []
                    try:
                        raw_items = json.loads(res_text)
                    except Exception:
                        matches = re.findall(r'\[\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[\'"]?([a-zA-Z]+)[\'"]?)?\s*\]', res_text)
                        raw_items = [[int(x), int(y), t or 'w'] for x, y, t in matches]

                    # 💡 全体座標への換算＆近接マージ（しきい値15）
                    for item in raw_items:
                        if isinstance(item, list) and len(item) >= 2:
                            local_x = item[0]
                            local_y = item[1]
                            ant_type = "queen" if (len(item) > 2 and str(item[2]).lower() in ["q", "queen"]) else "worker"

                            global_x = int((crop_x0 + (local_x / 1000.0) * crop_w) / cur_w * 1000.0)
                            global_y = int((crop_y0 + (local_y / 1000.0) * crop_h) / cur_h * 1000.0)

                            is_duplicate = False
                            for existing in ants_coords:
                                dist = ((existing["x"] - global_x)**2 + (existing["y"] - global_y)**2)**0.5
                                if dist < 15:
                                    is_duplicate = True
                                    if ant_type == "queen":
                                        existing["type"] = "queen"
                                    break

                            if not is_duplicate:
                                ants_coords.append({"x": global_x, "y": global_y, "type": ant_type})

                    time.sleep(0.5)

                status_box.empty()
                api_elapsed = time.time() - api_start_time

            except Exception as e:
                status_box.error(f"スキャン中にエラーが発生しました: {e}")
                st.stop()

            ai_count = len(ants_coords)
            elapsed_time = time.time() - start_time

            st.session_state["orig_image"] = orig_image
            st.session_state["ai_ants"] = ants_coords
            st.session_state["orig_width"] = orig_w
            st.session_state["orig_height"] = orig_h
            st.session_state["elapsed_time"] = elapsed_time
            st.session_state["api_elapsed"] = api_elapsed

            st.success(f"✨ 高精度スキャン完了！（検出総数: {ai_count}匹 / 処理時間: {elapsed_time:.1f}秒 / モデル: {MODEL_NAME}）")

    # --- 解析結果 ＆ 手動調整キャンバス ---
    if "ai_ants" in st.session_state:
        st.markdown("---")
        st.subheader("🎯 解析結果 ＆ 手動調整（追加・削除）")
        st.write(
            "**➕ 追加（青点）** で見落としを足し、**🗑️ 削除（黄色点）** で誤検知を消去できます。"
        )

        edit_mode = st.radio(
            "ペンツールの種類を選択",
            ["➕ 追加 (青点)", "🗑️ 削除 (黄色点)"],
            horizontal=True,
            key="edit_mode_radio",
        )

        current_stroke = "#0000FF" if "追加" in edit_mode else "#FFCC00"
        current_fill = "rgba(0, 0, 255, 0.4)" if "追加" in edit_mode else "rgba(255, 204, 0, 0.6)"

        orig_w = st.session_state["orig_width"]
        orig_h = st.session_state["orig_height"]
        max_canvas_width = 750
        scale = max_canvas_width / orig_w
        canvas_width = max_canvas_width
        canvas_height = int(orig_h * scale)

        base_annotated = st.session_state["orig_image"].copy()
        draw_base = ImageDraw.Draw(base_annotated)
        radius = max(5, int(orig_w * 0.0055))
        ai_ants = st.session_state["ai_ants"]

        def draw_crown(draw, cx, cy, size):
            half = int(size * 1.8)
            points = [
                (cx - half, cy + half),
                (cx + half, cy + half),
                (cx + half, cy - half * 0.5),
                (cx + half * 0.5, cy - half),
                (cx, cy - half * 0.5),
                (cx - half * 0.5, cy - half),
                (cx - half, cy - half * 0.5),
            ]
            draw.polygon(points, fill="#FFD700", outline="white", width=2)

        for ant in ai_ants:
            if isinstance(ant, dict):
                px = int(ant.get("x", 0) * orig_w / 1000)
                py = int(ant.get("y", 0) * orig_h / 1000)
                ant_type = ant.get("type", "worker")

                if ant_type == "queen":
                    draw_crown(draw_base, px, py, radius)
                else:
                    draw_base.ellipse(
                        [px - radius, py - radius, px + radius, py + radius],
                        fill="red",
                        outline="white",
                        width=2,
                    )

        canvas_result = st_canvas(
            fill_color=current_fill,
            stroke_width=3,
            stroke_color=current_stroke,
            background_image=base_annotated,
            update_streamlit=True,
            height=canvas_height,
            width=canvas_width,
            drawing_mode="point",
            key="canvas_edit_mode",
        )

        manual_adds = []
        manual_deletes = []

        if canvas_result.json_data is not None:
            for obj in canvas_result.json_data.get("objects", []):
                img_x = int(obj.get("left", 0) / scale)
                img_y = int(obj.get("top", 0) / scale)
                stroke_color = obj.get("stroke", "").lower()
                if "ffcc" in stroke_color or "yellow" in stroke_color or "#ffcc00" in stroke_color:
                    manual_deletes.append((img_x, img_y))
                else:
                    manual_adds.append((img_x, img_y))

        valid_ai_ants = []
        for ant in ai_ants:
            if not isinstance(ant, dict):
                continue
            ax = int(ant.get("x", 0) * orig_w / 1000)
            ay = int(ant.get("y", 0) * orig_h / 1000)

            is_deleted = False
            for dx, dy in manual_deletes:
                dist = ((ax - dx) ** 2 + (ay - dy) ** 2) ** 0.5
                if dist < 18:
                    is_deleted = True
                    break

            if not is_deleted:
                valid_ai_ants.append(ant)

        final_image = st.session_state["orig_image"].copy()
        draw_final = ImageDraw.Draw(final_image)

        queen_count = 0
        for ant in valid_ai_ants:
            px = int(ant.get("x", 0) * orig_w / 1000)
            py = int(ant.get("y", 0) * orig_h / 1000)
            ant_type = ant.get("type", "worker")

            if ant_type == "queen":
                queen_count += 1
                draw_crown(draw_final, px, py, radius)
            else:
                draw_final.ellipse(
                    [px - radius, py - radius, px + radius, py + radius],
                    fill="red",
                    outline="white",
                    width=2,
                )

        for ax, ay in manual_adds:
            draw_final.ellipse(
                [ax - radius, ay - radius, ax + radius, ay + radius],
                fill="blue",
                outline="white",
                width=2,
            )

        final_ai_count = len(valid_ai_ants)
        added_count = len(manual_adds)
        deleted_count = len(manual_deletes)
        total_count = final_ai_count + added_count

        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("📸 確定プレビュー")
            st.image(final_image, use_container_width=True)

        with col2:
            st.subheader("📊 集計サマリー")
            st.metric(
                label="🏁 確定カウント数",
                value=f"{total_count} 匹",
                delta=f"追加+{added_count} / 削除-{deleted_count}" if (added_count > 0 or deleted_count > 0) else None
            )
            st.markdown("---")
            st.metric(label="AI有効検出数", value=f"{final_ai_count} 匹")
            if queen_count > 0:
                st.metric(label="👑 女王検出", value=f"{queen_count} 匹")
            st.metric(label="手動追加（青）", value=f"{added_count} 個")
            st.metric(label="削除指定（黄色）", value=f"{deleted_count} 個")

            st.markdown("---")
            if "elapsed_time" in st.session_state:
                st.caption(
                    f"⏱️ 全体: {st.session_state['elapsed_time']:.1f}秒<br>"
                    f"（API: {st.session_state.get('api_elapsed', 0):.1f}秒）",
                    unsafe_allow_html=True
                )

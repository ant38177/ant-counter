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
    page_title="Ant Worker Counter (思考ステップ搭載版)",
    page_icon="🐜",
    layout="centered"
)

st.title("🐜 Ant Worker Counter")
st.write("AIに「部屋ごとの観察・思考プロセス」を踏ませることで、多重カウントを防止した高精度モデル！")

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

# 💡 スキャンモードの選択
scan_mode = st.sidebar.radio(
    "スキャン方式の選択",
    ["🧠 全体・思考スキャン（オオアリ・標準コロニー推奨）", "🔍 田の字4分割ズーム（微小アリ・超密集用）"],
    index=0
)

# モデル選択
model_options = {
    "gemini-3.1-flash-lite（🚀 超高速・無料枠制限なし）": "gemini-3.1-flash-lite",
    "gemini-flash-latest（🌟 標準・安定・高精度）": "gemini-flash-latest",
    "gemini-3.8-flash（🎯 最新知能・超高精度 ※混雑時待機あり）": "gemini-3.8-flash",
}

selected_label = st.sidebar.selectbox(
    "AIモデルを選択",
    list(model_options.keys()),
    index=0
)
MODEL_NAME = model_options[selected_label]

st.sidebar.caption(f"現在のモデル: `{MODEL_NAME}`")

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

        if st.button("🎯 高精度解析を実行する", type="primary"):
            start_time = time.time()
            client = genai.Client(api_key=api_key)

            orig_w, orig_h = orig_image.size
            max_size = 1400
            proc_img = orig_image.copy()
            if max(orig_w, orig_h) > max_size:
                proc_img.thumbnail((max_size, max_size))

            cur_w, cur_h = proc_img.size
            status_box = st.empty()
            ants_coords = []
            ai_thoughts = ""
            api_start_time = time.time()

            try:
                # ==========================================
                # モード1: 🧠 全体・思考スキャン（今回のオオアリに最適！）
                # ==========================================
                if "全体" in scan_mode:
                    status_box.info("🧠 巣全体と部屋の構造を分析中...")

                    img_buf = io.BytesIO()
                    proc_img.save(img_buf, format="JPEG", quality=95)
                    img_bytes = img_buf.getvalue()

                    # 💡 【核心：まず思考メモ（analysis）を書かせてから座標を出させるプロンプト】
                    prompt = (
                        "You are an expert entomologist conducting a precise ant census.\n"
                        "First, examine the whole nest and understand the scale (large ants vs small ants).\n"
                        "CRITICAL RULES:\n"
                        "1. Place exactly ONE point per ant on its thorax (body center). NEVER place multiple points on the same ant's head, gaster, or legs!\n"
                        "2. In clusters, separate distinct individuals.\n"
                        "3. Identify the queen distinctly (large body/thorax).\n"
                        "STEP 1: In 'analysis', briefly summarize how many ants are in each room/chamber and where the queen is.\n"
                        "STEP 2: In 'ants', list coordinates x, y (0 to 1000) and type ('worker' or 'queen').\n"
                        "Return strictly a JSON object formatted as:\n"
                        '{"analysis": "Left chamber: ~10 ants, Right chamber: ~12 ants, Bottom chamber: 1 queen and ~8 workers.", '
                        '"ants": [{"x": 150, "y": 200, "type": "worker"}, {"x": 350, "y": 800, "type": "queen"}]}'
                    )

                    resp = None
                    for attempt in range(3):
                        try:
                            resp = client.models.generate_content(
                                model=MODEL_NAME,
                                contents=[
                                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                                    prompt
                                ],
                                config=types.GenerateContentConfig(
                                    response_mime_type="application/json",
                                    max_output_tokens=3000,
                                )
                            )
                            break
                        except Exception as e:
                            err_str = str(e)
                            if "503" in err_str or "UNAVAILABLE" in err_str:
                                if attempt < 2:
                                    status_box.warning(f"⚠️ サーバー混雑中。3秒後に自動再開します（{attempt+1}/3）...")
                                    time.sleep(3.0)
                                else:
                                    raise e
                            elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                                if attempt < 2:
                                    status_box.warning(f"⚠️ 無料枠待機中…12秒待機します（{attempt+1}/3）...")
                                    time.sleep(12.0)
                                else:
                                    raise e
                            else:
                                raise e

                    res_text = resp.text.strip() if resp and resp.text else "{}"
                    res_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", res_text)

                    try:
                        data = json.loads(res_text)
                        ai_thoughts = data.get("analysis", "")
                        ants_list = data.get("ants", [])
                        for item in ants_list:
                            ants_coords.append({
                                "x": int(item.get("x", 0)),
                                "y": int(item.get("y", 0)),
                                "type": item.get("type", "worker")
                            })
                    except Exception:
                        dict_matches = re.findall(r'["\']?x["\']?\s*[:=]\s*(\d+)\D+["\']?y["\']?\s*[:=]\s*(\d+)', res_text)
                        for xs, ys in dict_matches:
                            ants_coords.append({"x": int(xs), "y": int(ys), "type": "worker"})

                # ==========================================
                # モード2: 🔍 田の字4分割ズーム（超密集・微小アリ用）
                # ==========================================
                else:
                    split_x = int(cur_w * 0.5)
                    split_y = int(cur_h * 0.5)
                    overlap_x = int(cur_w * 0.08)
                    overlap_y = int(cur_h * 0.08)

                    quadrants = [
                        {"name": "左上", "box": (0, 0, split_x + overlap_x, split_y + overlap_y)},
                        {"name": "右上", "box": (split_x - overlap_x, 0, cur_w, split_y + overlap_y)},
                        {"name": "左下", "box": (0, split_y - overlap_y, split_x + overlap_x, cur_h)},
                        {"name": "右下", "box": (split_x - overlap_x, split_y - overlap_y, cur_w, cur_h)},
                    ]

                    for idx, quad in enumerate(quadrants):
                        status_box.info(f"🔍 [{idx+1}/4] {quad['name']} をスキャン中...")
                        crop_x0, crop_y0, crop_x1, crop_y1 = quad["box"]
                        crop_w, crop_h = crop_x1 - crop_x0, crop_y1 - crop_y0
                        cropped_img = proc_img.crop(quad["box"])

                        img_buf = io.BytesIO()
                        cropped_img.save(img_buf, format="JPEG", quality=92)
                        img_bytes = img_buf.getvalue()

                        prompt = (
                            f"Detect every ant in this {quad['name']} image. Place exactly ONE coordinate per ant on the thorax.\n"
                            "Do NOT place multiple points on one ant. Identify queen as 'q'. "
                            "Format: [[x,y,'w'],[x,y,'q']]. Coordinates 0 to 1000."
                        )

                        resp = client.models.generate_content(
                            model=MODEL_NAME,
                            contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), prompt],
                            config=types.GenerateContentConfig(response_mime_type="application/json", max_output_tokens=1500)
                        )
                        res_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.text.strip())

                        raw_items = []
                        try:
                            raw_items = json.loads(res_text)
                        except Exception:
                            matches = re.findall(r'\[\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[\'"]?([a-zA-Z]+)[\'"]?)?\s*\]', res_text)
                            raw_items = [[int(x), int(y), t or 'w'] for x, y, t in matches]

                        for item in raw_items:
                            if isinstance(item, list) and len(item) >= 2:
                                lx, ly = item[0], item[1]
                                at = "queen" if (len(item) > 2 and str(item[2]).lower() in ["q", "queen"]) else "worker"
                                gx = int((crop_x0 + (lx / 1000.0) * crop_w) / cur_w * 1000.0)
                                gy = int((crop_y0 + (ly / 1000.0) * crop_h) / cur_h * 1000.0)

                                if not any(((e["x"] - gx)**2 + (e["y"] - gy)**2)**0.5 < 20 for e in ants_coords):
                                    ants_coords.append({"x": gx, "y": gy, "type": at})

                        time.sleep(0.4)

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
            st.session_state["ai_thoughts"] = ai_thoughts

            st.success(f"✨ 解析完了！（検出総数: {ai_count}匹 / 処理時間: {elapsed_time:.1f}秒）")

    # --- 解析結果 ＆ 手動調整キャンバス ---
    if "ai_ants" in st.session_state:
        # 💡 AIの観察メモを表示
        if st.session_state.get("ai_thoughts"):
            st.info(f"🧠 **AIの観察メモ**: {st.session_state['ai_thoughts']}")

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
        radius = max(6, int(orig_w * 0.007))
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
                if dist < 22:
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

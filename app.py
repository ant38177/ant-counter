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
    page_title="Ant Worker Counter (500匹対応・王冠検出)",
    page_icon="🐜",
    layout="centered"
)

st.title("🐜 Ant Worker Counter")
st.write("最大500匹対応！長辺1600px・女王自動検出と手動微調整（追加/削除）ツール")

# --- 🔑 APIキーの自動読み込み＆手動入力設定 ---
# 1. あなた（管理者）が使う場合: Secretsから全自動で取得（入力不要）
secrets_key = ""
if "GEMINI_API_KEY" in st.secrets:
    secrets_key = st.secrets["GEMINI_API_KEY"]

# 2. サイドバーにキー入力欄を設置（あなた自身は最初から自動入力された状態になります）
st.sidebar.header("⚙️ 設定")
api_key = st.sidebar.text_input(
    "Gemini APIキー (無料)",
    value=secrets_key,
    type="password",
    help="Secretsにキーが設定されている場合は自動で入力済みになります。別のキーを使いたい場合のみ上書きしてください。"
)

if not secrets_key and not api_key:
    st.sidebar.markdown(
        "[👉 無料のGemini APIキーを取得する (Google AI Studio)](https://aistudio.google.com/app/apikey)"
    )

# モデル選択
selected_model = st.sidebar.selectbox(
    "AIモデル",
    ["gemini-3.8-flash (標準・高精度)", "gemini-3.1-flash-lite (超高速・制限に強い)"],
    index=0
)
model_name = "gemini-3.8-flash" if "3.8" in selected_model else "gemini-3.1-flash-lite"

# --- 画像アップローダー ---
uploaded_file = st.file_uploader(
    "アリのケース・巣の写真を選択",
    type=["jpg", "jpeg", "png"],
)

if uploaded_file:
    if not api_key:
        st.error("⚠️ APIキーが見つかりません。サイドバーにGemini APIキーを入力してください。")
    else:
        orig_image = Image.open(uploaded_file)
        st.image(orig_image, caption="アップロードされた画像", use_container_width=True)

        if st.button("🎯 解析と王冠プロットを実行する", type="primary"):
            start_time = time.time()
            client = genai.Client(api_key=api_key)

            orig_width, orig_height = orig_image.size

            # 長辺1600pxにリサイズ（細部を維持しつつトークン制限を防御）
            max_size = 1600
            proc_image = orig_image.copy()
            if max(orig_width, orig_height) > max_size:
                proc_image.thumbnail((max_size, max_size))

            # JPEGに圧縮して送信サイズを軽量化
            img_byte_arr = io.BytesIO()
            proc_image.save(img_byte_arr, format="JPEG", quality=85)
            img_bytes = img_byte_arr.getvalue()

            # 💡 【500匹対応・超軽量プロンプト】
            # 短縮配列 [[x, y, "w"], [x, y, "q"]] で返すことでトークンを1/3に節約！
            prompt = (
                "You are an expert entomology and computer vision assistant. "
                "Detect EVERY SINGLE ant (worker) in this image with maximum precision up to 500+ ants. "
                "Also, if the queen ant is present, identify her distinctly. "
                "Coordinates x and y must be integers from 0 to 1000 relative to image size. "
                "Return ONLY a compact raw JSON 2D array: "
                "[[x, y, 'w'], [x, y, 'q']]. "
                "Use 'w' for worker ant and 'q' for queen ant. "
                "Strictly return JSON array only. No text, no markdown."
            )

            # ⏱️ 429制限（無料枠のクールダウン）をスマートに待機するリトライループ
            response = None
            max_retries = 3
            status_placeholder = st.empty()

            for attempt in range(max_retries):
                try:
                    status_placeholder.info(f"⏳ 画像を解析中...（モデル: {model_name}）")
                    api_start = time.time()

                    response = client.models.generateContent(
                        model=model_name,
                        contents=[
                            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                            prompt
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            # 500匹 × 約4トークン ＝ 約2000トークン。3500あれば500匹全部が余裕で入ります！
                            max_output_tokens=3500,
                        )
                    )
                    api_elapsed = time.time() - api_start
                    status_placeholder.empty()
                    break

                except APIError as e:
                    err_text = str(e)
                    if "429" in err_text or "RESOURCE_EXHAUSTED" in err_text:
                        wait_sec = (attempt + 1) * 15
                        for sec in range(wait_sec, 0, -1):
                            status_placeholder.warning(
                                f"⚠️ 無料枠の1分間リクエスト制限を検知しました。安全のため **あと{sec}秒** 待機して自動再開します（試行 {attempt+1}/{max_retries}）..."
                            )
                            time.sleep(1)
                    else:
                        status_placeholder.error(f"APIエラーが発生しました: {e}")
                        st.stop()

            if not response or not response.text:
                st.error("⚠️ 制限またはタイムアウトにより応答が得られませんでした。少し時間を置いて再度お試しください。")
                st.stop()

            response_text = response.text.strip()
            # マークダウンのバッククォートがあれば除去
            if response_text.startswith("```"):
                response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
                response_text = re.sub(r"\s*```$", "", response_text)

            ants_coords = []

            # 💡 【パース処理】超軽量配列 [[x, y, "w"], ...] と 旧来の辞書形式の両方に対応
            try:
                result_data = json.loads(response_text)
                if isinstance(result_data, list):
                    for item in result_data:
                        if isinstance(item, list) and len(item) >= 2:
                            ant_type = "queen" if (len(item) > 2 and str(item[2]).lower() in ["q", "queen"]) else "worker"
                            ants_coords.append({"x": int(item[0]), "y": int(item[1]), "type": ant_type})
                        elif isinstance(item, dict):
                            ant_type = item.get("type", "worker")
                            ants_coords.append({"x": int(item.get("x", 0)), "y": int(item.get("y", 0)), "type": ant_type})
                elif isinstance(result_data, dict):
                    for v in result_data.values():
                        if isinstance(v, list):
                            for item in v:
                                if isinstance(item, list) and len(item) >= 2:
                                    ant_type = "queen" if (len(item) > 2 and str(item[2]).lower() in ["q", "queen"]) else "worker"
                                    ants_coords.append({"x": int(item[0]), "y": int(item[1]), "type": ant_type})
                                elif isinstance(item, dict):
                                    ants_coords.append({"x": int(item.get("x", 0)), "y": int(item.get("y", 0)), "type": item.get("type", "worker")})
                            break
            except Exception:
                pass

            # フォールバック正規表現救出
            if not ants_coords:
                # [123, 456, 'w'] パターン
                array_matches = re.findall(r'\[\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[\'"]?([a-zA-Z]+)[\'"]?)?\s*\]', response_text)
                if array_matches:
                    for x_str, y_str, t_str in array_matches:
                        ant_type = "queen" if t_str and t_str.lower() in ["q", "queen"] else "worker"
                        ants_coords.append({"x": int(x_str), "y": int(y_str), "type": ant_type})
                else:
                    # {"x": 123, "y": 456} パターン
                    dict_matches = re.findall(r'["\']?x["\']?\s*[:=]\s*(\d+)\D+["\']?y["\']?\s*[:=]\s*(\d+)', response_text, re.IGNORECASE)
                    for x_str, y_str in dict_matches:
                        ants_coords.append({"x": int(x_str), "y": int(y_str), "type": "worker"})

            ai_count = len(ants_coords)

            if ai_count == 0:
                st.error("⚠️ 座標データを取得できませんでした。")
                with st.expander("🔍 AIからの生レスポンスを確認"):
                    st.text(response_text)
                st.stop()

            elapsed_time = time.time() - start_time
            st.session_state["orig_image"] = orig_image
            st.session_state["ai_ants"] = ants_coords
            st.session_state["orig_width"] = orig_width
            st.session_state["orig_height"] = orig_height
            st.session_state["elapsed_time"] = elapsed_time
            st.session_state["api_elapsed"] = api_elapsed

            st.success(f"✨ 解析完了！（全体: {elapsed_time:.1f}秒 / API: {api_elapsed:.1f}秒 / 検出総数: {ai_count}匹）")

    # --- 解析結果 ＆ 手動調整キャンバス ---
    if "ai_ants" in st.session_state:
        st.markdown("---")
        st.subheader("🎯 解析結果 ＆ 手動調整（追加・削除）")
        st.write(
            "モードを選択して画像をクリックしてください。"
            " **➕ 追加（青点）** で見落としを足し、**🗑️ 削除（黄色点）** で誤検知を消去できます。"
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
        max_canvas_width = 600
        scale = max_canvas_width / orig_w
        canvas_width = max_canvas_width
        canvas_height = int(orig_h * scale)

        base_annotated = st.session_state["orig_image"].copy()
        draw_base = ImageDraw.Draw(base_annotated)
        radius = max(6, int(orig_w * 0.007))
        ai_ants = st.session_state["ai_ants"]

        # 王冠を描画する関数
        def draw_crown(draw, cx, cy, size):
            half = int(size * 1.5)
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

        # 手動クリック用キャンバス
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
            objects = canvas_result.json_data.get("objects", [])
            for obj in objects:
                canvas_x = obj.get("left", 0)
                canvas_y = obj.get("top", 0)
                img_x = int(canvas_x / scale)
                img_y = int(canvas_y / scale)

                stroke_color = obj.get("stroke", "").lower()
                if "ffcc" in stroke_color or "yellow" in stroke_color or "#ffcc00" in stroke_color:
                    manual_deletes.append((img_x, img_y))
                else:
                    manual_adds.append((img_x, img_y))

        # 削除指定（黄色点）の近くにある点を除外
        valid_ai_ants = []
        for ant in ai_ants:
            if not isinstance(ant, dict):
                continue
            ax = int(ant.get("x", 0) * orig_w / 1000)
            ay = int(ant.get("y", 0) * orig_h / 1000)

            is_deleted = False
            for dx, dy in manual_deletes:
                dist = ((ax - dx) ** 2 + (ay - dy) ** 2) ** 0.5
                if dist < 25:
                    is_deleted = True
                    break

            if not is_deleted:
                valid_ai_ants.append(ant)

        # 最終プレビュー描画
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

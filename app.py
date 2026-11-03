import streamlit as st
from PIL import Image, ImageDraw
import json
import time
import io
import math
from streamlit_drawable_canvas import st_canvas
from google import genai
from google.genai import types

# ---------------------------------------------------------
# ページ設定
# ---------------------------------------------------------
st.set_page_config(
    page_title="アリカウンター",
    page_icon="🐜",
    layout="wide"
)

# ---------------------------------------------------------
# 認証・サイドバー設定
# ---------------------------------------------------------
query_params = st.query_params
is_admin = query_params.get("admin") == "ant"
secrets_api_key = st.secrets.get("GEMINI_API_KEY", "")

with st.sidebar:
    st.header("設定")
    
    if is_admin and secrets_api_key:
        st.success("👑 管理者モード（認証済み）")
        api_key = secrets_api_key
    else:
        api_key = st.text_input(
            "Gemini APIキー",
            type="password",
            placeholder="AIzaSy...",
            help="Google AI Studioで取得したAPIキーを入力してください。"
        )
        if not api_key:
            st.caption("🔑 [Google AI StudioでAPIキーを取得](https://aistudio.google.com/app/apikey)")

    st.markdown("---")
    
    # スキャン方式の選択
    st.subheader("スキャン方式の選択")
    scan_mode = st.radio(
        "モードを選択",
        [
            "🧠 全体スキャン（オオアリ・少数コロニー向け）",
            "🔍 田の字4分割ズーム（蜜壺アリ・密集100匹以上向け）"
        ],
        index=0
    )
    is_grid = "4分割" in scan_mode

    st.markdown("---")
    st.subheader("AIモデルの選択")
    model_choice = st.selectbox(
        "スキャンに使用するモデル",
        options=[
            ("gemini-3.1-flash-lite", "gemini-3.1-flash-lite（無料枠に強い・高速）"),
            ("gemini-flash-latest", "gemini-flash-latest（標準・安定）"),
            ("gemini-3.8-flash", "gemini-3.8-flash（最新知能）")
        ],
        format_func=lambda x: x[1],
        index=0
    )[0]

# ---------------------------------------------------------
# タイトル
# ---------------------------------------------------------
st.title("🐜 アリカウンター")
st.caption("写真からアリを自動検出し、手動で追加・削除の微調整ができます。")

# ---------------------------------------------------------
# プロンプト定義
# ---------------------------------------------------------
SCAN_PROMPT = """
画像内のアリをカウントし、各アリの中心座標を出力してください。

【ルール】
1. 画像全体を見てアリのサイズ感を把握し、脚や影ではなく「頭部と腹部をつなぐ中央の胴体（胸部: thorax）」のど真ん中に点を打ってください。
2. 1匹のアリに対して出力する座標は厳密に1つだけです。アリがいない場所には絶対に座標を出さないでください。
3. 女王アリ（他の個体より明らかに体格が巨大な個体）が存在する場合は "is_queen": true とし、通常の働きアリは "is_queen": false にしてください。

必ず以下のJSON形式のみを返してください：
{
  "ants": [
    {"y": 120, "x": 450, "is_queen": false},
    {"y": 145, "x": 820, "is_queen": true}
  ]
}
※ yとxは画像の左上を (0,0)、右下を (1000,1000) とする0〜1000の整数正規化座標です。
"""

# ---------------------------------------------------------
# 単一画像スキャンAPI呼び出し
# ---------------------------------------------------------
def scan_image(client: genai.Client, image: Image.Image, model_name: str):
    img_byte_arr = io.BytesIO()
    rgb_img = image.convert("RGB")
    rgb_img.save(img_byte_arr, format='JPEG', quality=95)
    img_bytes = img_byte_arr.getvalue()
    
    contents = [
        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
        SCAN_PROMPT
    ]
    config = types.GenerateContentConfig(
        temperature=0.0,
        max_output_tokens=3500,
        response_mime_type="application/json"
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            res = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )
            text = res.text.strip()
            if text.startswith("```json"): text = text[7:]
            if text.startswith("```"): text = text[3:]
            if text.endswith("```"): text = text[:-3]
            data = json.loads(text.strip())
            return data.get("ants", [])
        except Exception as e:
            if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and attempt < max_retries - 1:
                time.sleep((attempt + 1) * 3)
            elif attempt < max_retries - 1:
                time.sleep(2)
            else:
                return []
    return []

# ---------------------------------------------------------
# 田の字4分割ズームスキャン（密集用）
# ---------------------------------------------------------
def run_grid_scan(raw_image: Image.Image, api_key: str, model_name: str, progress_bar, status_box):
    client = genai.Client(api_key=api_key)
    orig_w, orig_h = raw_image.size
    
    overlap = 0.08
    tile_defs = [
        ("左上", 0.0, 0.0, 0.5 + overlap, 0.5 + overlap),
        ("右上", 0.5 - overlap, 0.0, 1.0, 0.5 + overlap),
        ("左下", 0.0, 0.5 - overlap, 0.5 + overlap, 1.0),
        ("右下", 0.5 - overlap, 0.5 - overlap, 1.0, 1.0)
    ]
    
    all_ants_pixel = []
    
    for i, (name, x1_r, y1_r, x2_r, y2_r) in enumerate(tile_defs):
        progress_bar.progress((i) / 4.0)
        status_box.info(f"スキャン中... ({i+1}/4: {name}区画)")
        
        px1 = int(x1_r * orig_w)
        py1 = int(y1_r * orig_h)
        px2 = min(orig_w, int(x2_r * orig_w))
        py2 = min(orig_h, int(y2_r * orig_h))
        
        tile_w = px2 - px1
        tile_h = py2 - py1
        
        tile_img = raw_image.crop((px1, py1, px2, py2))
        tile_ants = scan_image(client, tile_img, model_name)
        
        for ant in tile_ants:
            local_x = ant["x"] / 1000.0
            local_y = ant["y"] / 1000.0
            
            global_px = px1 + (local_x * tile_w)
            global_py = py1 + (local_y * tile_h)
            
            all_ants_pixel.append({
                "px": global_px,
                "py": global_py,
                "is_queen": ant.get("is_queen", False)
            })
            
        progress_bar.progress((i + 0.8) / 4.0)
        if i < 3:
            time.sleep(1.0)
            
    progress_bar.progress(1.0)
    status_box.empty()
    
    # 適切な重複マージ（原寸ピクセルベースで約18px）
    merge_threshold_px = max(16.0, orig_w * 0.015)
    merged_ants = []
    
    for ant in all_ants_pixel:
        duplicate = False
        for m in merged_ants:
            dx = ant["px"] - m["px"]
            dy = ant["py"] - m["py"]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < merge_threshold_px:
                duplicate = True
                if ant.get("is_queen", False):
                    m["is_queen"] = True
                break
        if not duplicate:
            merged_ants.append(ant)
            
    final_ants = []
    for m in merged_ants:
        final_ants.append({
            "x": int((m["px"] / orig_w) * 1000.0),
            "y": int((m["py"] / orig_h) * 1000.0),
            "is_queen": m.get("is_queen", False)
        })
        
    return final_ants

# ---------------------------------------------------------
# セッション状態
# ---------------------------------------------------------
if "detected_ants" not in st.session_state:
    st.session_state.detected_ants = []
if "image_analyzed" not in st.session_state:
    st.session_state.image_analyzed = False
if "current_image" not in st.session_state:
    st.session_state.current_image = None
if "image_id" not in st.session_state:
    st.session_state.image_id = None

# ---------------------------------------------------------
# 写真アップロード & 実行
# ---------------------------------------------------------
uploaded_file = st.file_uploader("写真をアップロードしてください（JPG, PNG）", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    if st.session_state.image_id != uploaded_file.name + str(len(file_bytes)):
        st.session_state.image_id = uploaded_file.name + str(len(file_bytes))
        st.session_state.current_image = Image.open(io.BytesIO(file_bytes))
        st.session_state.detected_ants = []
        st.session_state.image_analyzed = False

    raw_image = st.session_state.current_image
    orig_w, orig_h = raw_image.size

    if st.button("スキャン実行", type="primary"):
        if not api_key:
            st.error("APIキーを入力してください。")
        else:
            prog = st.progress(0.0)
            status_box = st.empty()
            try:
                if is_grid:
                    # 4分割ズームスキャン
                    ants = run_grid_scan(raw_image, api_key, model_choice, prog, status_box)
                else:
                    # 全体スキャン（画像切断なし・オオアリ向け）
                    status_box.info("全体スキャン中...")
                    client = genai.Client(api_key=api_key)
                    ants = scan_image(client, raw_image, model_choice)
                    prog.progress(1.0)
                    status_box.empty()
                    
                st.session_state.detected_ants = ants
                st.session_state.image_analyzed = True
                st.success(f"スキャン完了：{len(ants)} 匹検出")
            except Exception as e:
                status_box.error(f"エラーが発生しました: {e}")

    # ---------------------------------------------------------
    # 手動調整キャンバス
    # ---------------------------------------------------------
    if st.session_state.image_analyzed:
        st.markdown("---")
        st.subheader("手動調整（追加・削除）")
        st.caption("➕ 追加（青点）で見落としを足し、🗑️ 削除（黄色点）で誤検知をクリックして消去できます。")

        display_w = 900
        scale = display_w / orig_w
        display_h = int(orig_h * scale)
        resized_img = raw_image.resize((display_w, display_h))

        # 背景画像に検出点を描画
        annotated_bg = resized_img.copy()
        draw = ImageDraw.Draw(annotated_bg)
        r = 6
        for ant in st.session_state.detected_ants:
            px = int((ant["x"] / 1000.0) * display_w)
            py = int((ant["y"] / 1000.0) * display_h)
            if ant.get("is_queen", False):
                draw.ellipse((px - r - 3, py - r - 3, px + r + 3, py + r + 3), fill="#f59e0b", outline="#ffffff", width=2)
                draw.text((px - 5, py - 18), "👑", fill="#f59e0b")
            else:
                draw.ellipse((px - r, py - r, px + r, py + r), fill="#ef4444", outline="#ffffff", width=2)

        tool_col1, _ = st.columns([1, 3])
        with tool_col1:
            tool_mode = st.radio("ツール", ["➕ 追加 (青点)", "🗑️ 削除 (黄色点)"], index=0)

        is_add_mode = "追加" in tool_mode
        current_color = "#3b82f6" if is_add_mode else "#eab308"

        canvas_result = st_canvas(
            fill_color=current_color,
            stroke_width=2,
            stroke_color="#ffffff",
            background_image=annotated_bg,
            update_streamlit=True,
            height=display_h,
            width=display_w,
            drawing_mode="point",
            point_display_radius=6,
            key=f"canvas_{is_grid}",
        )

        # 手動調整の集計
        manual_added_coords = []
        deleted_indices = set()

        if canvas_result.json_data is not None:
            objects = canvas_result.json_data.get("objects", [])
            for obj in objects:
                cx = obj.get("left", 0)
                cy = obj.get("top", 0)
                fill_str = str(obj.get("fill", "")).lower()
                stroke_str = str(obj.get("stroke", "")).lower()
                
                is_blue = ("3b82f6" in fill_str or "rgb(59" in fill_str or "blue" in fill_str or
                           "3b82f6" in stroke_str or "rgb(59" in stroke_str)
                is_yellow = ("eab308" in fill_str or "rgb(234" in fill_str or "yellow" in fill_str or
                             "eab308" in stroke_str or "rgb(234" in stroke_str)

                if is_blue:
                    manual_added_coords.append((cx, cy))
                elif is_yellow:
                    closest_idx = -1
                    min_dist = 25.0
                    for idx, ant in enumerate(st.session_state.detected_ants):
                        px = (ant["x"] / 1000.0) * display_w
                        py = (ant["y"] / 1000.0) * display_h
                        dist = math.sqrt((cx - px) ** 2 + (cy - py) ** 2)
                        if dist < min_dist:
                            min_dist = dist
                            closest_idx = idx
                    if closest_idx != -1:
                        deleted_indices.add(closest_idx)

        ai_valid_ants = [
            ant for i, ant in enumerate(st.session_state.detected_ants)
            if i not in deleted_indices
        ]
        
        queen_count = sum(1 for a in ai_valid_ants if a.get("is_queen", False))
        worker_count = len(ai_valid_ants) - queen_count + len(manual_added_coords)
        total_count = queen_count + worker_count

        # ---------------------------------------------------------
        # 集計サマリ & 保存
        # ---------------------------------------------------------
        st.markdown("---")
        sum_col1, sum_col2 = st.columns([1, 1])

        with sum_col1:
            st.subheader("集計サマリ")
            st.metric("総計カウント数", f"{total_count} 匹")
            st.write(f"👑 女王アリ: {queen_count} 匹 ｜ 🐜 働きアリ: {worker_count} 匹")
            st.caption(f"（内訳: AI検出 {len(ai_valid_ants)} ｜ 追加 +{len(manual_added_coords)} ｜ 削除 -{len(deleted_indices)}）")

        with sum_col2:
            st.subheader("画像の保存")
            final_img = raw_image.copy()
            final_draw = ImageDraw.Draw(final_img)
            orig_r = max(5, int(orig_w * 0.007))

            for ant in ai_valid_ants:
                fx = int((ant["x"] / 1000.0) * orig_w)
                fy = int((ant["y"] / 1000.0) * orig_h)
                if ant.get("is_queen", False):
                    final_draw.ellipse((fx - orig_r - 4, fy - orig_r - 4, fx + orig_r + 4, fy + orig_r + 4), fill="#f59e0b", outline="#ffffff", width=3)
                else:
                    final_draw.ellipse((fx - orig_r, fy - orig_r, fx + orig_r, fy + orig_r), fill="#ef4444", outline="#ffffff", width=2)

            for (cx, cy) in manual_added_coords:
                fx = int((cx / display_w) * orig_w)
                fy = int((cy / display_h) * orig_h)
                final_draw.ellipse((fx - orig_r, fy - orig_r, fx + orig_r, fy + orig_r), fill="#3b82f6", outline="#ffffff", width=2)

            buf = io.BytesIO()
            final_img.save(buf, format="JPEG", quality=95)
            st.download_button(
                label="カウント結果画像をダウンロード",
                data=buf.getvalue(),
                file_name="ant_count_result.jpg",
                mime="image/jpeg",
                use_container_width=True
            )

        with st.expander("確定プレビュー", expanded=True):
            preview_thumb = final_img.resize((display_w, display_h))
            st.image(preview_thumb, caption=f"合計 {total_count} 匹")
else:
    st.info("カウントしたいアリの写真をアップロードしてください。")

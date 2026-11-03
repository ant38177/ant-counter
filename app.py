import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import json
import time
import io
import math
from streamlit_drawable_canvas import st_canvas
from google import genai
from google.genai import types

# ---------------------------------------------------------
# ページ設定 & スタイル
# ---------------------------------------------------------
st.set_page_config(
    page_title="アリカウンター (Ant Worker Counter)",
    page_icon="🐜",
    layout="wide"
)

st.markdown("""
<style>
    .reportview-container { background: #f8f9fa; }
    .main-title { font-size: 2.2rem; font-weight: 700; color: #1e293b; margin-bottom: 0.2rem; }
    .sub-title { font-size: 1.0rem; color: #64748b; margin-bottom: 1.5rem; }
    .metric-card { background: white; padding: 1.2rem; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-left: 5px solid #3b82f6; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 認証・サイドバー設定（無料枠 & セキュリティ完全対応）
# ---------------------------------------------------------
query_params = st.query_params
is_admin = query_params.get("admin") == "ant"
secrets_api_key = st.secrets.get("GEMINI_API_KEY", "")

with st.sidebar:
    st.header("⚙️ 設定")
    
    if is_admin and secrets_api_key:
        st.success("👑 管理者モード（認証済み）")
        api_key = secrets_api_key
    else:
        st.info("💡 Google AI Studio の無料APIキーをご利用いただけます。")
        api_key = st.text_input(
            "Gemini APIキー",
            type="password",
            placeholder="AIzaSy...",
            help="Google AI Studioで取得した無料のAPIキーを入力してください。"
        )
        if not api_key:
            st.caption("🔑 [Google AI StudioでAPIキーを無料取得する](https://aistudio.google.com/app/apikey)")

    st.markdown("---")
    st.subheader("AIモデルの選択")
    model_choice = st.selectbox(
        "スキャンに使用するモデル",
        options=[
            ("gemini-3.1-flash-lite", "gemini-3.1-flash-lite（🚀 超高速・無料枠に強い・推奨）"),
            ("gemini-flash-latest", "gemini-flash-latest（☀️ 標準・安定）"),
            ("gemini-3.8-flash", "gemini-3.8-flash（🧠 最新知能・思考スキャン）")
        ],
        format_func=lambda x: x[1],
        index=0
    )[0]
    st.caption(f"現在のモデル: `{model_choice}`")

# ---------------------------------------------------------
# タイトル・概要
# ---------------------------------------------------------
st.markdown("<div class='main-title'>🐜 アリカウンター (Ant Worker Counter)</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>超密集したアリも取りこぼさない高精度グリッドスキャン ＆ 手動微調整カウンター</div>", unsafe_allow_html=True)

# ---------------------------------------------------------
# スキャン用プロンプト
# ---------------------------------------------------------
SCAN_PROMPT = """
画像内のすべてのアリを数えます。
1. アリのサイズ感を把握し、頭・胸・腹の1個体に対して1つの中心座標を出力してください（1匹に複数の点をつけてはいけません）。
2. 画像の特徴や背景、容器の形状に関係なく、Y座標の上（0%）から下（100%）へ水平に漏れなくスキャンしてください。
3. 密集部、重なり、影にいる微小な個体も決して省略せず、すべて出力してください。
4. 女王アリ（体格が明らかに巨大な個体）がいる場合のみ "is_queen": true とし、通常の働きアリは "is_queen": false にしてください。

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
# 単一タイルのスキャンAPI
# ---------------------------------------------------------
def scan_single_image(client: genai.Client, image: Image.Image, model_name: str):
    img_byte_arr = io.BytesIO()
    rgb_img = image.convert("RGB")
    rgb_img.save(img_byte_arr, format='JPEG', quality=95)
    img_bytes = img_byte_arr.getvalue()
    
    contents = [
        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
        SCAN_PROMPT
    ]
    config = types.GenerateContentConfig(
        temperature=0.1,
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
# 幾何学グリッド（自動4分割＆統合）スキャン
# どんな写真でも解像度を確保し85匹飽和リミットを突破する
# ---------------------------------------------------------
def run_grid_scan(raw_image: Image.Image, api_key: str, model_name: str, progress_bar):
    client = genai.Client(api_key=api_key)
    orig_w, orig_h = raw_image.size
    
    # 2x2の均等グリッド（重複率 8%）
    overlap = 0.08
    tiles = [
        # (box_x1, box_y1, box_x2, box_y2)
        ("左上", 0.0, 0.0, 0.5 + overlap, 0.5 + overlap),
        ("右上", 0.5 - overlap, 0.0, 1.0, 0.5 + overlap),
        ("左下", 0.0, 0.5 - overlap, 0.5 + overlap, 1.0),
        ("右下", 0.5 - overlap, 0.5 - overlap, 1.0, 1.0)
    ]
    
    all_ants = []
    
    for i, (name, x1_ratio, y1_ratio, x2_ratio, y2_ratio) in enumerate(tiles):
        progress_bar.progress((i + 1) / 4, text=f"🔍 幾何学グリッドを精密スキャン中... ({i+1}/4: {name}区画)")
        
        # タイルの切り出し
        box = (
            int(x1_ratio * orig_w),
            int(y1_ratio * orig_h),
            int(x2_ratio * orig_w),
            int(y2_ratio * orig_h)
        )
        tile_img = raw_image.crop(box)
        
        tile_ants = scan_single_image(client, tile_img, model_name)
        
        # タイル内の正規化座標(0-1000)を、画像全体の正規化座標(0-1000)に逆変換
        for ant in tile_ants:
            tile_local_x = ant["x"] / 1000.0
            tile_local_y = ant["y"] / 1000.0
            
            global_x_ratio = x1_ratio + tile_local_x * (x2_ratio - x1_ratio)
            global_y_ratio = y1_ratio + tile_local_y * (y2_ratio - y1_ratio)
            
            all_ants.append({
                "x": int(global_x_ratio * 1000.0),
                "y": int(global_y_ratio * 1000.0),
                "is_queen": ant.get("is_queen", False)
            })
            
        time.sleep(0.5)  # API負荷軽減
        
    # 重複マージ（ユークリッド距離が 20 未満の点は統合）
    merged_ants = []
    for ant in all_ants:
        duplicate = False
        for m in merged_ants:
            dx = ant["x"] - m["x"]
            dy = ant["y"] - m["y"]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < 22:  # 重複判定のしきい値
                duplicate = True
                if ant.get("is_queen", False):
                    m["is_queen"] = True
                break
        if not duplicate:
            merged_ants.append(ant)
            
    return merged_ants

# ---------------------------------------------------------
# セッション状態の初期化
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
# 画像アップロード
# ---------------------------------------------------------
uploaded_file = st.file_uploader("📷 アリの写真をアップロードしてください（JPG, PNG）", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    if st.session_state.image_id != uploaded_file.name + str(len(file_bytes)):
        st.session_state.image_id = uploaded_file.name + str(len(file_bytes))
        st.session_state.current_image = Image.open(io.BytesIO(file_bytes))
        st.session_state.detected_ants = []
        st.session_state.image_analyzed = False

    raw_image = st.session_state.current_image
    orig_w, orig_h = raw_image.size

    col_btn, col_info = st.columns([1, 2])
    with col_btn:
        start_scan = st.button("🔍 アリを自動スキャンする", type="primary", use_container_width=True)
    with col_info:
        st.caption("※ 幾何学グリッド走査により、密集したアリの飽和見落としを防いで全数カウントします。")

    if start_scan:
        if not api_key:
            st.error("⚠️ サイドバーでGemini APIキーを入力してください。")
        else:
            prog = st.progress(0, text="スキャン準備中...")
            try:
                ants = run_grid_scan(raw_image, api_key, model_choice, prog)
                prog.progress(1.0, text="スキャン完了！")
                st.session_state.detected_ants = ants
                st.session_state.image_analyzed = True
                st.success(f"🎉 スキャン完了！ 合計 {len(ants)} 匹のアリを検出しました。")
            except Exception as e:
                st.error(f"❌ スキャン中にエラーが発生しました: {e}")

    # ---------------------------------------------------------
    # 解析結果表示 & 手動調整キャンバス
    # ---------------------------------------------------------
    if st.session_state.image_analyzed:
        st.markdown("---")
        st.subheader("🎯 解析結果 & 手動調整（追加・削除）")
        st.markdown(
            "➕ **追加（青点）** で見落としを足し、🗑️ **削除（黄色点）** で誤検知（点の上をクリック）を消去できます。"
        )

        display_w = 900
        scale = display_w / orig_w
        display_h = int(orig_h * scale)
        resized_img = raw_image.resize((display_w, display_h))

        # AI初期検出点を背景に描画
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

        # ツール選択
        tool_col1, tool_col2 = st.columns([1, 3])
        with tool_col1:
            tool_mode = st.radio(
                "ペンツールの種類を選択",
                ["➕ 追加 (青点)", "🗑️ 削除 (黄色点)"],
                index=0
            )

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
            key="ant_canvas_v2",
        )

        # ---------------------------------------------------------
        # 手動クリックの精密解析（追加・削除の完全反映）
        # ---------------------------------------------------------
        manual_added_coords = []  # [(x, y)] display座標
        deleted_indices = set()

        if canvas_result.json_data is not None:
            objects = canvas_result.json_data.get("objects", [])
            for obj in objects:
                # pointオブジェクトから中心座標を取得
                cx = obj.get("left", 0)
                cy = obj.get("top", 0)
                
                # 色の判定（fill または stroke）
                fill_str = str(obj.get("fill", "")).lower()
                stroke_str = str(obj.get("stroke", "")).lower()
                
                # 青色判定（追加）
                is_blue_point = ("3b82f6" in fill_str or "rgb(59" in fill_str or "blue" in fill_str or
                                 "3b82f6" in stroke_str or "rgb(59" in stroke_str)
                # 黄色判定（削除）
                is_yellow_point = ("eab308" in fill_str or "rgb(234" in fill_str or "yellow" in fill_str or
                                   "eab308" in stroke_str or "rgb(234" in stroke_str)

                if is_blue_point:
                    manual_added_coords.append((cx, cy))
                elif is_yellow_point:
                    # クリック地点から最も近いAI検出点（半径25px以内）を検索して削除
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

        # 有効なAI検出点
        ai_valid_ants = [
            ant for i, ant in enumerate(st.session_state.detected_ants)
            if i not in deleted_indices
        ]
        
        queen_count = sum(1 for a in ai_valid_ants if a.get("is_queen", False))
        worker_count = len(ai_valid_ants) - queen_count + len(manual_added_coords)
        total_count = queen_count + worker_count

        # ---------------------------------------------------------
        # 集計サマリ & 確定プレビュー
        # ---------------------------------------------------------
        st.markdown("---")
        sum_col1, sum_col2 = st.columns([1, 1])

        with sum_col1:
            st.subheader("📊 集計サマリ")
            st.metric("総計カウント数", f"{total_count} 匹")
            
            q_col, w_col = st.columns(2)
            with q_col:
                st.write(f"👑 **女王アリ**: {queen_count} 匹")
            with w_col:
                st.write(f"🐜 **働きアリ**: {worker_count} 匹")
                
            st.caption(f"（内訳: AI有効検出 {len(ai_valid_ants)} 匹 ｜ 手動追加 +{len(manual_added_coords)} 匹 ｜ 手動削除 -{len(deleted_indices)} 匹）")

        with sum_col2:
            st.subheader("💾 確定画像の保存")

            # 確定高解像度画像の生成（削除が消え、追加青点が反映された画像）
            final_img = raw_image.copy()
            final_draw = ImageDraw.Draw(final_img)
            orig_r = max(5, int(orig_w * 0.007))

            # 残ったAI検出点の描画
            for ant in ai_valid_ants:
                fx = int((ant["x"] / 1000.0) * orig_w)
                fy = int((ant["y"] / 1000.0) * orig_h)
                if ant.get("is_queen", False):
                    final_draw.ellipse((fx - orig_r - 4, fy - orig_r - 4, fx + orig_r + 4, fy + orig_r + 4), fill="#f59e0b", outline="#ffffff", width=3)
                else:
                    final_draw.ellipse((fx - orig_r, fy - orig_r, fx + orig_r, fy + orig_r), fill="#ef4444", outline="#ffffff", width=2)

            # 手動追加（青点）の描画
            for (cx, cy) in manual_added_coords:
                fx = int((cx / display_w) * orig_w)
                fy = int((cy / display_h) * orig_h)
                final_draw.ellipse((fx - orig_r, fy - orig_r, fx + orig_r, fy + orig_r), fill="#3b82f6", outline="#ffffff", width=2)

            buf = io.BytesIO()
            final_img.save(buf, format="JPEG", quality=95)
            st.download_button(
                label="📥 確定カウント画像（手動調整反映済み）を保存",
                data=buf.getvalue(),
                file_name="ant_confirmed_count.jpg",
                mime="image/jpeg",
                use_container_width=True
            )

        # 画面下部に確定プレビューを表示（削除された赤点が消え、青点が合成された状態）
        with st.expander("👁️ 確定プレビューを確認（削除・追加が正しく反映された全体像）", expanded=True):
            preview_thumb = final_img.resize((display_w, display_h))
            st.image(preview_thumb, caption=f"確定カウントプレビュー: 合計 {total_count} 匹（赤=AI検出, 青=手動追加, 王冠=女王）")
else:
    st.info("👆 カウントしたいアリの写真をアップロードしてください。")

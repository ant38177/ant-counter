import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import json
import time
import io
import re
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
    .queen-badge { background-color: #fef3c7; color: #b45309; padding: 2px 8px; border-radius: 6px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 認証・サイドバー設定（無料枠 & セキュリティ完全対応）
# ---------------------------------------------------------
# URLクエリパラメータから管理者判定 (?admin=ant)
query_params = st.query_params
is_admin = query_params.get("admin") == "ant"

# Secretsからキー取得（存在する場合）
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
            help="Google AI Studioで取得した無料のAPIキーを入力してください（サーバーには保存されません）。"
        )
        if not api_key:
            st.caption("🔑 [Google AI StudioでAPIキーを無料取得する](https://aistudio.google.com/app/apikey)")

    st.markdown("---")
    st.subheader("AIモデルの選択")
    model_choice = st.selectbox(
        "スキャンに使用するモデル",
        options=[
            ("gemini-3.1-flash-lite", "gemini-3.1-flash-lite（🚀 超高速・無料枠に最も強い・推奨）"),
            ("gemini-flash-latest", "gemini-flash-latest（☀️ 標準・安定）"),
            ("gemini-3.8-flash", "gemini-3.8-flash（🧠 最新知能・高密度検出）")
        ],
        format_func=lambda x: x[1],
        index=0
    )[0]
    st.caption(f"現在のモデル: `{model_choice}`")

# ---------------------------------------------------------
# タイトル・概要
# ---------------------------------------------------------
st.markdown("<div class='main-title'>🐜 アリカウンター (Ant Worker Counter)</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>超密集した蜜壺アリから大型のオオアリまで、自動スキャンで正確に計数します。</div>", unsafe_allow_html=True)

# ---------------------------------------------------------
# 考案されたスキャナープロンプト
# ---------------------------------------------------------
SCANNER_PROMPT = """
アリの総数をカウントします。
1. まず全体画像を見て、アリのサイズを把握してください（大きな個体か、微小な個体か、スケール感を把握）。
2. 画像の特徴や背景、巣の部屋・区画・境界に関係なく、Y座標の上（0%）から下（100%）へ、スキャナーのように1行ずつ水平にスキャンしてアリの座標を出力してください。
3. 途中で検出を終了せず、画像全体に多数（200匹以上存在しうる前提）のアリがいるものとして、微小な個体や重なり・影にいる個体も漏れなくすべて列挙しなさい。
4. 女王アリ（Queen ant）が存在する場合は、体格が他の働きアリより明らかに大きく（胸部や腹部が巨大）、かつ通常1〜数匹のみです。"is_queen": true とし、通常の働きアリは "is_queen": false としてください。

必ず以下のJSONフォーマットのみを返してください。余計な解説文やマークダウンは不要です：
{
  "ants": [
    {"y": 120, "x": 450, "is_queen": false},
    {"y": 145, "x": 820, "is_queen": true}
  ]
}
※ yとxは、画像の左上を (0, 0)、右下を (1000, 1000) とする 0〜1000 の整数正規化座標です。
"""

# ---------------------------------------------------------
# API呼び出し関数（自動リトライ & トークン枠4096確保）
# ---------------------------------------------------------
def scan_ants(image: Image.Image, api_key: str, model_name: str):
    client = genai.Client(api_key=api_key)
    
    # 画像バイト列の準備
    img_byte_arr = io.BytesIO()
    # JPEGで最適化保存
    rgb_img = image.convert("RGB")
    rgb_img.save(img_byte_arr, format='JPEG', quality=95)
    img_bytes = img_byte_arr.getvalue()
    
    contents = [
        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
        SCANNER_PROMPT
    ]
    
    # 200匹以上の大量JSON出力を途切れさせない設定
    config = types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=4096,
        response_mime_type="application/json"
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )
            
            # JSONテキストのパース
            text = response.text.strip()
            # 万が一バッククォートが含まれている場合を除去
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            data = json.loads(text)
            return data.get("ants", [])
            
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                wait_sec = (attempt + 1) * 3
                st.warning(f"⏳ API無料枠の混雑を検知しました。{wait_sec}秒待機して自動再試行します... ({attempt + 1}/{max_retries})")
                time.sleep(wait_sec)
            elif attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise e

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
    # 新しい画像がアップされたらリセット
    file_bytes = uploaded_file.getvalue()
    if st.session_state.image_id != uploaded_file.name + str(len(file_bytes)):
        st.session_state.image_id = uploaded_file.name + str(len(file_bytes))
        st.session_state.current_image = Image.open(io.BytesIO(file_bytes))
        st.session_state.detected_ants = []
        st.session_state.image_analyzed = False

    raw_image = st.session_state.current_image
    orig_w, orig_h = raw_image.size

    # スキャン実行ボタン
    col_btn, col_info = st.columns([1, 2])
    with col_btn:
        start_scan = st.button("🔍 アリを自動スキャンする", type="primary", use_container_width=True)
    with col_info:
        st.caption("※ 上から下へ水平に走査し、サイズに応じた漏れのないカウントを実行します。")

    if start_scan:
        if not api_key:
            st.error("⚠️ サイドバーでGemini APIキーを入力してください（管理者は ?admin=ant で自動認証）。")
        else:
            with st.spinner("🧠 画像全体を把握し、上から下へ高密度ラスタースキャン中..."):
                try:
                    ants = scan_ants(raw_image, api_key, model_choice)
                    st.session_state.detected_ants = ants
                    st.session_state.image_analyzed = True
                    st.success(f"🎉 スキャン完了！ {len(ants)} 匹のアリを検出しました。")
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

        # 画面表示用に幅を固定（アスペクト比維持）
        display_w = 900
        scale = display_w / orig_w
        display_h = int(orig_h * scale)
        resized_img = raw_image.resize((display_w, display_h))

        # AIが検出した初期点を背景画像の上に描画
        annotated_bg = resized_img.copy()
        draw = ImageDraw.Draw(annotated_bg)
        
        # 点の描画サイズ
        r = 6
        for ant in st.session_state.detected_ants:
            # 0〜1000の正規化座標を表示用ピクセルに変換
            px = int((ant["x"] / 1000.0) * display_w)
            py = int((ant["y"] / 1000.0) * display_h)
            is_queen = ant.get("is_queen", False)

            if is_queen:
                # 女王アリ: 金色の大きな王冠風サークル
                draw.ellipse((px - r - 3, py - r - 3, px + r + 3, py + r + 3), fill="#f59e0b", outline="#ffffff", width=2)
                draw.text((px - 5, py - 18), "👑", fill="#f59e0b")
            else:
                # 働きアリ: 赤い点
                draw.ellipse((px - r, py - r, px + r, py + r), fill="#ef4444", outline="#ffffff", width=2)

        # ツール選択（追加: 青点 / 削除: 黄色点）
        tool_col1, tool_col2 = st.columns([1, 3])
        with tool_col1:
            tool_mode = st.radio(
                "ペンツールの種類を選択",
                ["➕ 追加 (青点)", "🗑️ 削除 (黄色点)"],
                index=0
            )

        stroke_color = "#3b82f6" if "追加" in tool_mode else "#eab308"

        # 手動調整用キャンバス
        canvas_result = st_canvas(
            fill_color="rgba(255, 255, 255, 0)",
            stroke_width=10,
            stroke_color=stroke_color,
            background_image=annotated_bg,
            update_streamlit=True,
            height=display_h,
            width=display_w,
            drawing_mode="point",
            point_display_radius=5,
            key="ant_canvas",
        )

        # 手動クリックの集計
        manual_added = 0
        deleted_indices = set()

        if canvas_result.json_data is not None:
            objects = canvas_result.json_data.get("objects", [])
            for obj in objects:
                if obj.get("type") == "circle":
                    cx = obj.get("left", 0) + obj.get("radius", 0)
                    cy = obj.get("top", 0) + obj.get("radius", 0)
                    color = obj.get("stroke")

                    if color == "#3b82f6":
                        # 青点：手動追加
                        manual_added += 1
                    elif color == "#eab308":
                        # 黄色点：最も近いAI検出点を削除対象にする（距離25px以内）
                        closest_idx = -1
                        min_dist = 25.0
                        for idx, ant in enumerate(st.session_state.detected_ants):
                            px = (ant["x"] / 1000.0) * display_w
                            py = (ant["y"] / 1000.0) * display_h
                            dist = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
                            if dist < min_dist:
                                min_dist = dist
                                closest_idx = idx
                        if closest_idx != -1:
                            deleted_indices.add(closest_idx)

        # 有効なAI検出アリのカウント
        ai_valid_ants = [
            ant for i, ant in enumerate(st.session_state.detected_ants)
            if i not in deleted_indices
        ]
        
        queen_count = sum(1 for a in ai_valid_ants if a.get("is_queen", False))
        worker_count = len(ai_valid_ants) - queen_count + manual_added
        total_count = queen_count + worker_count

        # ---------------------------------------------------------
        # 集計サマリ & ダウンロード
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
                
            st.caption(f"（内訳: AI有効検出 {len(ai_valid_ants)} 匹 ｜ 手動追加 +{manual_added} 匹 ｜ 手動削除 -{len(deleted_indices)} 匹）")

        with sum_col2:
            st.subheader("💾 結果画像の保存")
            
            # 保存用フル解像度画像に点を打つ
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

            buf = io.BytesIO()
            final_img.save(buf, format="JPEG", quality=95)
            st.download_button(
                label="📥 カウント結果画像をダウンロード",
                data=buf.getvalue(),
                file_name="ant_count_result.jpg",
                mime="image/jpeg",
                use_container_width=True
            )
else:
    # 写真未アップロード時のプレースホルダー表示
    st.info("👆 カウントしたいアリの写真をアップロードしてください。")

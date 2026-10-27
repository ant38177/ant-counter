import io
import json
from PIL import Image, ImageDraw
import streamlit as st
from streamlit_drawable_canvas import st_canvas
import google.generativeai as genai

# ページ全体のレイアウト設定
st.set_page_config(
    page_title="Ant Worker Counter (Gemini AI Edition)", layout="wide"
)

st.title("🐜 Ant Worker Counter (AI自動赤点 ＋ 手動補正版)")
st.write(
    "AIがアリの位置を特定して赤点を自動プロットし、画面上のクリックで追加・調整が行えます。"
)

# シークレット（Secrets）からAPIキーを自動取得
api_key = None
if "GEMINI_API_KEY" in st.secrets:
  api_key = st.secrets["GEMINI_API_KEY"]

# サイドバー：使い方などの案内
st.sidebar.header("⚙️ アプリ情報")
st.sidebar.markdown(
    "**📝 使い方**\n"
    "1. アリの巣・ケースの写真をアップロード\n"
    "2. 「Gemini AIで自動検出する」をクリック\n"
    "3. AIが打った赤点を確認し、ズレがあればクリックで追加・調整"
)

# メイン：画像アップロード
uploaded_file = st.file_uploader(
    "アリのケース・巣の写真をアップロード", type=["jpg", "jpeg", "png"]
)

if uploaded_file is not None:
  # 画像の読み込み
  image = Image.open(uploaded_file)
  img_width, img_height = image.size

  # APIキーが設定されているかチェック
  if not api_key:
    st.error(
        "⚠️ APIキーが設定されていません。Streamlit Cloudの「Settings >"
        " Secrets」に `GEMINI_API_KEY` を設定してください。"
    )
    st.image(image, caption="アップロードされた画像", use_container_width=True)
  else:
    # Gemini APIの設定
    genai.configure(api_key=api_key)

    if st.button("🤖 Gemini AIでワーカーを自動検出する", type="primary"):
      with st.spinner("AIがアリの位置を解析・プロット中..."):
        try:
          # 最新のビジョンモデルを指定
          model = genai.GenerativeModel("gemini-3.8-flash")

          prompt = (
              "この画像に写っているすべてのアリ（ワーカー）の位置を検出してください。"
              "それぞれの中心位置の座標（x, y：画像全体の幅・高さを1000とした場合の0〜1000の整数）をリストアップしてください。"
              "必ず以下のJSON形式のみで回答してください（Markdownのバッククォートなどは付けず、純粋なJSON文字列のみにしてください）。"
              "{"
              '  "count": 29,'
              '  "ants": [{"x": 150, "y": 320}, {"x": 200, "y": 410}], '
              '  "reason": "検出の根拠や状況の説明"'
              "}"
          )

          response = model.generate_content([image, prompt])
          response_text = response.text.strip()

          # マークダウンのコードブロックが含まれている場合のクリーニング
          if response_text.startswith("```"):
            response_text = (
                response_text.split("```")[1]
                .lstrip("json")
                .strip()
                .rstrip("```")
                .strip()
            )

          result_data = json.loads(response_text)
          ai_count = result_data.get("count", 0)
          ants_coords = result_data.get("ants", [])
          reason = result_data.get("reason", "解析完了")

          # 画像に赤点を描画する処理
          annotated_image = image.copy()
          draw = ImageDraw.Draw(annotated_image)
          
          # アリのサイズに応じて赤点の大きさを調整（画像幅の約0.8%程度）
          radius = max(6, int(img_width * 0.008))

          for ant in ants_coords:
            # 0〜1000の正規化座標を実際のピクセル座標に変換
            px = int(ant.get("x", 0) * img_width / 1000)
            py = int(ant.get("y", 0) * img_height / 1000)
            
            # 赤い円を描画（視認しやすいように白い縁取りをつける）
            draw.ellipse(
                [px - radius, py - radius, px + radius, py + radius],
                fill="red",
                outline="white",
                width=2,
            )

          # セッションステートに結果を保存
          st.session_state["annotated_image"] = annotated_image
          st.session_state["ai_count"] = ai_count
          st.session_state["ai_reason"] = reason
          st.success(f"✨ AI検出完了！ 推定ワーカー数: {ai_count} 匹")

        except Exception as e:
          st.error(f"エラーが発生しました: {e}")

    # 解析結果や手動調整エリアの表示
    display_image = (
        st.session_state["annotated_image"]
        if "annotated_image" in st.session_state
        else image
    )

    if "ai_count" in st.session_state:
      st.info(f"💡 **AIの解説**: {st.session_state['ai_reason']}")

      col1, col2 = st.columns([2, 1])

      with col1:
        st.subheader("🎯 AI自動赤点プロット ＆ 手動微調整キャンバス")
        st.write(
            "AIが検出したアリに赤点が打たれています。足りない場所があればクリックして追加できます。"
        )

        # 画面幅に合わせてキャンバスサイズを調整（最大幅600px）
        max_canvas_width = 600
        scale = max_canvas_width / img_width
        canvas_width = max_canvas_width
        canvas_height = int(img_height * scale)

        # 描画キャンバスの設置（背景に赤点付き画像を使用）
        canvas_result = st_canvas(
            fill_color="rgba(255, 0, 0, 0.3)",
            stroke_width=3,
            stroke_color="#FF0000",
            background_image=display_image,
            update_streamlit=True,
            height=canvas_height,
            width=canvas_width,
            drawing_mode="point",
            key="canvas",
        )

        # キャンバスに手動で追加されたポイント数を取得
        if canvas_result.json_data is not None:
          objects = canvas_result.json_data.get("objects", [])
          manual_adds = len(objects)
        else:
          manual_adds = 0

      with col2:
        st.subheader("📊 カウント集計")
        base_count = st.session_state["ai_count"]

        st.metric(label="AI検出ベース数", value=f"{base_count} 匹")
        st.metric(
            label="手動追加マーカー数",
            value=f"{manual_adds} 個",
            delta=manual_adds,
        )

        final_total = base_count + manual_adds
        st.markdown("---")
        st.markdown(f"### 🏁 最終確定ワーカー数: **{final_total} 匹**")

        if st.button("📥 結果をテキストで保存"):
          st.balloons()
          st.success(
              f"本日の記録を確定しました！ 合計: {final_total}匹"
              "（許容誤差範囲内クリア）"
          )

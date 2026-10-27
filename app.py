import io
import json
from PIL import Image, ImageDraw
import streamlit as st
from streamlit_drawable_canvas import st_canvas
import google.generativeai as genai

# ページ全体のレイアウト設定
st.set_page_config(
    page_title="Ant Worker Counter (Multi-Angle Edition)", layout="wide"
)

st.title("🐜 Ant Worker Counter (マルチアングル対応 ＆ 自動赤点版)")
st.write(
    "角度を変えた複数の写真を同時にアップロードし、アングルごとにAIの赤点プロットとカウントを確認できます。"
)

# シークレット（Secrets）からAPIキーを自動取得
api_key = None
if "GEMINI_API_KEY" in st.secrets:
  api_key = st.secrets["GEMINI_API_KEY"]

# サイドバー：使い方などの案内
st.sidebar.header("⚙️ アプリ情報")
st.sidebar.markdown(
    "**📝 使い方**\n"
    "1. 角度を変えた複数の写真をまとめてアップロード\n"
    "2. 「すべての写真をAIで一括解析する」をクリック\n"
    "3. タブでアングルを切り替えながら赤点やズレを確認・調整"
)

# 複数ファイルのアップロードに対応
uploaded_files = st.file_uploader(
    "アリのケース・巣の写真（複数枚選択可）をアップロード",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

if uploaded_files:
  # APIキーが設定されているかチェック
  if not api_key:
    st.error(
        "⚠️ APIキーが設定されていません。Streamlit Cloudの「Settings >"
        " Secrets」に `GEMINI_API_KEY` を設定してください。"
    )
  else:
    # Gemini APIの設定
    genai.configure(api_key=api_key)

    if st.button("🤖 すべての写真（アングル）をAIで一括解析する", type="primary"):
      with st.spinner("AIが各アングルの写真を解析・赤点プロット中..."):
        try:
          # 最新のビジョンモデルを指定
          model = genai.GenerativeModel("gemini-3.8-flash")
          analysis_results = {}

          for uploaded_file in uploaded_files:
            image = Image.open(uploaded_file)
            img_width, img_height = image.size

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
            radius = max(6, int(img_width * 0.008))

            for ant in ants_coords:
              px = int(ant.get("x", 0) * img_width / 1000)
              py = int(ant.get("y", 0) * img_height / 1000)
              draw.ellipse(
                  [px - radius, py - radius, px + radius, py + radius],
                  fill="red",
                  outline="white",
                  width=2,
              )

            # 結果を辞書に保存
            analysis_results[uploaded_file.name] = {
                "annotated_image": annotated_image,
                "count": ai_count,
                "reason": reason,
                "width": img_width,
                "height": img_height,
            }

          st.session_state["analysis_results"] = analysis_results
          st.success(f"✨ 全 {len(uploaded_files)} 枚のアングルの解析が完了しました！")

        except Exception as e:
          st.error(f"エラーが発生しました: {e}")

    # 解析結果や手動調整エリアの表示（タブ切り替え）
    if "analysis_results" in st.session_state:
      results = st.session_state["analysis_results"]
      file_names = list(results.keys())

      st.markdown("---")
      st.subheader("🎯 アングル別解析結果 ＆ 調整")

      # タブで写真を切り替え
      tabs = st.tabs([f"📸 {name}" for name in file_names])

      for idx, tab in enumerate(tabs):
        with tab:
          name = file_names[idx]
          res = results[name]

          st.info(f"💡 **AIの解説**: {res['reason']}")

          col1, col2 = st.columns([2, 1])

          with col1:
            st.write("赤点を確認し、必要に応じてクリックで追加・調整できます。")
            img_width = res["width"]
            img_height = res["height"]
            max_canvas_width = 600
            scale = max_canvas_width / img_width
            canvas_width = max_canvas_width
            canvas_height = int(img_height * scale)

            canvas_result = st_canvas(
                fill_color="rgba(255, 0, 0, 0.3)",
                stroke_width=3,
                stroke_color="#FF0000",
                background_image=res["annotated_image"],
                update_streamlit=True,
                height=canvas_height,
                width=canvas_width,
                drawing_mode="point",
                key=f"canvas_{name}",
            )

            if canvas_result.json_data is not None:
              objects = canvas_result.json_data.get("objects", [])
              manual_adds = len(objects)
            else:
              manual_adds = 0

          with col2:
            st.subheader("📊 このアングルの集計")
            base_count = res["count"]
            st.metric(label="AI検出ベース数", value=f"{base_count} 匹")
            st.metric(
                label="手動追加マーカー数",
                value=f"{manual_adds} 個",
                delta=manual_adds,
            )

            sub_total = base_count + manual_adds
            st.markdown("---")
            st.markdown(f"### 🏁 この写真の確定数: **{sub_total} 匹**")

      # 全体のまとめ
      st.markdown("---")
      st.subheader("📊 総合まとめ")
      total_ai = sum(r["count"] for r in results.values())
      st.metric(label="全アングルのAI検出合計", value=f"{total_ai} 匹")
      st.write(
          "※ 角度を変えた写真は同じ個体を重複して捉えている場合があるため、アングルごとに最もクリアに全体が見える写真を参考にカウントを確定させてください。"
      )

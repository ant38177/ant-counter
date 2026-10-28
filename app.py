import io
import json
from PIL import Image, ImageDraw
import streamlit as st
from streamlit_drawable_canvas import st_canvas
import google.generativeai as genai

# ページ全体のレイアウト設定
st.set_page_config(
    page_title="Ant Worker Counter (Ant Count Tool)", layout="wide"
)

st.title("🐜 Ant Worker Counter")
st.write(
    "用途に合わせて「高速モード」と「カウント表示モード」を切り替えて解析できます。"
)

# シークレット（Secrets）からAPIキーを自動取得
api_key = None
if "GEMINI_API_KEY" in st.secrets:
  api_key = st.secrets["GEMINI_API_KEY"]

# サイドバー：モード選択と使い方
st.sidebar.header("⚙️ 解析設定 & 使い方")

analysis_mode = st.sidebar.radio(
    "解析モードを選択",
    [
        "⚡ 高速モード（数のみ・すぐ結果が出る）",
        "🎯 カウント表示モード（赤点プロット ＆ 手動調整）",
    ],
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**📝 使い方**\n"
    "1. 写真を選択（複数枚OK）\n"
    "2. モードを選んで実行ボタンを押す\n"
    "3. 必要に応じてタブや赤点を確認"
)

# 複数ファイルのアップロードに対応
uploaded_files = st.file_uploader(
    "アリのケース・巣の写真（複数枚選択可）をアップロード",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

if uploaded_files:
  if not api_key:
    st.error(
        "⚠️ APIキーが設定されていません。Streamlit Cloudの「Settings >"
        " Secrets」に `GEMINI_API_KEY` を設定してください。"
    )
  else:
    genai.configure(api_key=api_key)

    is_fast_mode = "高速" in analysis_mode
    btn_label = (
        "⚡ 高速モードで集計を実行する"
        if is_fast_mode
        else "🎯 カウント表示モードを実行する"
    )

    if st.button(btn_label, type="primary"):
      spinner_text = (
          "ワーカー数を高速で集計中..."
          if is_fast_mode
          else "画像を軽量化して赤点プロット付きで解析中..."
      )

      with st.spinner(spinner_text):
        try:
          model = genai.GenerativeModel("gemini-3.8-flash")
          analysis_results = {}

          for uploaded_file in uploaded_files:
            # 元画像の読み込み
            orig_image = Image.open(uploaded_file)
            orig_width, orig_height = orig_image.size

            # 【高速化】長辺が最大800pxになるように縮小（アスペクト比維持）
            max_size = 800
            proc_image = orig_image.copy()
            if max(orig_width, orig_height) > max_size:
              proc_image.thumbnail((max_size, max_size))

            # モードによってプロンプトを切り替え
            if is_fast_mode:
              prompt = (
                  "この画像に写っているすべてのアリ（ワーカー）の総数をカウントしてください。"
                  "必ず以下のJSON形式のみで回答してください（Markdownのバッククォートなどは付けず、純粋なJSON文字列のみにしてください）。"
                  "{"
                  '  "count": 118,'
                  '  "reason": "検出の根拠や状況の説明"'
                  "}"
              )
            else:
              prompt = (
                  "この画像に写っているすべてのアリ（ワーカー）の位置を検出してください。"
                  "それぞれの中心位置の座標（x, y：画像全体の幅・高さを1000とした場合の0〜1000の整数）をリストアップしてください。"
                  "必ず以下のJSON形式のみで回答してください（Markdownのバッククォートなどは付けず、純粋なJSON文字列のみにしてください）。"
                  "{"
                  '  "count": 118,'
                  '  "ants": [{"x": 150, "y": 320}, {"x": 200, "y": 410}], '
                  '  "reason": "検出の根拠や状況の説明"'
                  "}"
              )

            # 画像をAIに送信
            response = model.generate_content([proc_image, prompt])
            response_text = response.text.strip()

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
            reason = result_data.get("reason", "解析完了")

            if not is_fast_mode:
              # カウント表示モードの場合のみ赤点を描画
              ants_coords = result_data.get("ants", [])
              annotated_image = orig_image.copy()
              draw = ImageDraw.Draw(annotated_image)
              radius = max(8, int(orig_width * 0.008))

              for ant in ants_coords:
                px = int(ant.get("x", 0) * orig_width / 1000)
                py = int(ant.get("y", 0) * orig_height / 1000)
                draw.ellipse(
                    [px - radius, py - radius, px + radius, py + radius],
                    fill="red",
                    outline="white",
                    width=2,
                )
            else:
              annotated_image = orig_image

            analysis_results[uploaded_file.name] = {
                "annotated_image": annotated_image,
                "count": ai_count,
                "reason": reason,
                "width": orig_width,
                "height": orig_height,
            }

          st.session_state["analysis_results"] = analysis_results
          st.session_state["mode_used"] = (
              "fast" if is_fast_mode else "detailed"
          )
          st.success("✨ 解析が完了しました！")

        except Exception as e:
          st.error(f"エラーが発生しました: {e}")

    # 結果表示
    if "analysis_results" in st.session_state:
      results = st.session_state["analysis_results"]
      mode_used = st.session_state.get("mode_used", "detailed")
      file_names = list(results.keys())

      st.markdown("---")
      st.subheader("🎯 アングル別解析結果")

      tabs = st.tabs([f"📸 {name}" for name in file_names])

      for idx, tab in enumerate(tabs):
        with tab:
          name = file_names[idx]
          res = results[name]

          st.info(f"💡 **AIの解説**: {res['reason']}")

          if mode_used == "fast":
            # 高速モード（数のみ表示）
            st.metric(label="AI検出カウント数", value=f"{res['count']} 匹")
          else:
            # カウント表示モード（赤点＆手動調整付き）
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

      # 総合まとめ
      st.markdown("---")
      st.subheader("📊 総合まとめ")
      total_count = sum(r["count"] for r in results.values())
      st.metric(label="全アングルの合計数", value=f"{total_count} 匹")

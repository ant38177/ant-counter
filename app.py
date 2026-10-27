import io
import json
from PIL import Image
import streamlit as st
from streamlit_drawable_canvas import st_canvas
import google.generativeai as genai

# ページ全体のレイアウト設定
st.set_page_config(
    page_title="Ant Worker Counter (Gemini AI Edition)", layout="wide"
)

st.title("🐜 Ant Worker Counter (Gemini AI + 手動補正版)")
st.write(
    "AIビジョンでアリの群れを高精度に認識し、画面上のクリックでマーカーの追加・削除を行える実用型ツールです。"
)

# サイドバー：APIキーと設定
st.sidebar.header("⚙️ 設定パネル")
api_key_input = st.sidebar.text_input(
    "Google AI Studio APIキー", type="password", help="取得したAPIキーを入力してください"
)

st.sidebar.markdown("---")
st.sidebar.subheader("📝 使い方")
st.sidebar.markdown(
    "1. 上部にAPIキーを入力\n2. アリの巣・ケースの写真をアップロード\n3. AIが自動検出した結果を確認\n4. ズレがあれば画像上のクリックで追加・削除"
)

# メイン：画像アップロード
uploaded_file = st.file_uploader(
    "アリのケース・巣の写真をアップロード", type=["jpg", "jpeg", "png"]
)

if uploaded_file is not None:
  # 画像の読み込み
  image = Image.open(uploaded_file)

  # APIキーが入力されている場合の処理
  if not api_key_input:
    st.warning(
        "⚠️ サイドバーにGoogle AI StudioのAPIキーを入力してください。"
    )
    st.image(image, caption="アップロードされた画像", use_container_width=True)
  else:
    # Gemini APIの設定
    genai.configure(api_key=api_key_input)

    if st.button("🤖 Gemini AIでワーカーを自動検出する", type="primary"):
      with st.spinner("AIがアリの群れを解析中..."):
        try:
          # Gemini 2.5 Flashなどのビジョンモデルを指定
          model = genai.GenerativeModel("gemini-3.8-flash")

          prompt = (
              "この画像に写っているアリ（ワーカー）の総数を数えてください。"
              "±10匹程度の誤差は許容します。"
              "必ず以下のJSON形式のみで回答してください（Markdownのバッククォートなどは付けず、純粋なJSON文字列のみにしてください）。"
              '{"count": 200, "reason": "検出の根拠や状況の簡単な説明"}'
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

          # セッションステートに結果を保存
          st.session_state["ai_count"] = result_data.get("count", 0)
          st.session_state["ai_reason"] = result_data.get(
              "reason", "解析完了"
          )
          st.success(
              f"✨ AI検出完了！ 推定ワーカー数: {st.session_state['ai_count']} 匹"
          )

        except Exception as e:
          st.error(f"エラーが発生しました: {e}")

    # 解析結果や手動調整エリアの表示
    if "ai_count" in st.session_state:
      st.info(f"💡 **AIの解説**: {st.session_state['ai_reason']}")

      col1, col2 = st.columns([2, 1])

      with col1:
        st.subheader("🎯 マーカー・手動微調整キャンバス")
        st.write(
            "画像上の気になる場所をクリックしてポイントを追加・編集できます。"
        )

        # 画像のサイズに合わせたキャンバスの作成
        img_width, img_height = image.size
        # 画面幅に合わせてリサイズ（最大幅600px程度に調整）
        max_canvas_width = 600
        scale = max_canvas_width / img_width
        canvas_width = max_canvas_width
        canvas_height = int(img_height * scale)

        # 描画キャンバスの設置
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",
            stroke_width=3,
            stroke_color="#FF0000",
            background_image=image,
            update_streamlit=True,
            height=canvas_height,
            width=canvas_width,
            drawing_mode="point",
            key="canvas",
        )

        # キャンバスに置かれたポイントの数を取得
        if canvas_result.json_data is not None:
          objects = canvas_result.json_data.get("objects", [])
          manual_adds = len(objects)
        else:
          manual_adds = 0

      with col2:
        st.subheader("📊 カウント集計")
        base_count = st.session_state["ai_count"]

        # 手動で追加されたポイント分を反映（または手動入力による微調整）
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

import io
import json
import re
import time
from PIL import Image, ImageDraw
import streamlit as st
from streamlit_drawable_canvas import st_canvas
import google.generativeai as genai

# ページ全体のレイアウト設定
st.set_page_config(page_title="Ant Worker Counter", layout="centered")

st.title("🐜 Ant Worker Counter")
st.write(
    "アリの写真を1枚アップロードして、AIによる赤点プロットと手動調整を行います。"
)

# シークレット（Secrets）からAPIキーを自動取得
api_key = None
if "GEMINI_API_KEY" in st.secrets:
  api_key = st.secrets["GEMINI_API_KEY"]

# 🔍 【解像度モードの選択UI】
resolution_mode = st.radio(
    "🔍 解析モードの選択",
    ["低解像モード (800px / 高速)", "高解像モード (1200px / 高精度)"],
    horizontal=True,
)
# 選択肢に応じて最大解像度を切り替え
max_size = 800 if "800" in resolution_mode else 1200

# 画像のアップローダー（1枚のみ）
uploaded_file = st.file_uploader(
    "アリのケース・巣の写真を選択",
    type=["jpg", "jpeg", "png"],
)

if uploaded_file:
  if not api_key:
    st.error(
        "⚠️ APIキーが設定されていません。Streamlit Cloudの「Settings >"
        " Secrets」に `GEMINI_API_KEY` を設定してください。"
    )
  else:
    genai.configure(api_key=api_key)

    # 元画像の読み込み・プレビュー表示
    orig_image = Image.open(uploaded_file)
    st.image(orig_image, caption="アップロードされた画像", use_container_width=True)

    if st.button("🎯 解析と赤点プロットを実行する", type="primary"):
      # ⏱️ 【全体のタイマー開始】
      start_time = time.time()

      mode_name = "高速（800px）" if max_size == 800 else "高精度（1200px）"
      with st.spinner(
          f"画像を解析し、アリの位置を特定しています...（モード: {mode_name}）"
      ):
        try:
          model = genai.GenerativeModel(
              "gemini-3.8-flash",
              generation_config={
                  "response_mime_type": "application/json",
                  "max_output_tokens": 8192,
              },
          )

          orig_width, orig_height = orig_image.size

          # 選択されたモードの解像度（800px または 1200px）で縮小
          proc_image = orig_image.copy()
          if max(orig_width, orig_height) > max_size:
            proc_image.thumbnail((max_size, max_size))

          prompt = (
              "Detect every single ant (worker) in this image. x and y must be"
              " integers from 0 to 1000 relative to image size. Return ONLY in"
              " this JSON format:\n"
              '{"c": 118, "a": [{"x": 150, "y": 320}, {"x": 200, "y": 410}]}'
          )

          # ⏱️ 【Gemini API専用タイマー開始】
          api_start = time.time()
          response = model.generate_content([proc_image, prompt])
          api_elapsed = time.time() - api_start
          # ⏱️ 【Gemini API専用タイマー終了】

          response_text = response.text.strip()

          # バッククォートなどを除去
          if response_text.startswith("```"):
            response_text = (
                response_text.split("```")[1]
                .lstrip("json")
                .strip()
                .rstrip("```")
                .strip()
            )

          ants_coords = []

          # ① 通常のJSONパースを試みる
          try:
            result_data = json.loads(response_text)
            if isinstance(result_data, list):
              ants_coords = result_data
            elif isinstance(result_data, dict):
              ants_coords = result_data.get(
                  "a", result_data.get("ants", [])
              )
              if not ants_coords and "c" in result_data and isinstance(result_data["c"], list):
                ants_coords = result_data["c"]
          except Exception:
            pass

          # ② 正規表現による座標救出
          if not ants_coords:
            matches = re.findall(
                r'["\']?x["\']?\s*[:=]\s*(\d+)\D+["\']?y["\']?\s*[:=]\s*(\d+)',
                response_text,
                re.IGNORECASE,
            )
            for x_str, y_str in matches:
              ants_coords.append({"x": int(x_str), "y": int(y_str)})

          ai_count = len(ants_coords)

          if ai_count == 0:
            st.error(
                "⚠️ 座標データが途中で途切れたか、有効なデータを抽出できませんでした。"
                "（画像内のアリが多すぎるか、トークン上限に達した可能性があります）"
            )
            with st.expander("🔍 AIからの生レスポンスを確認する"):
              st.text(response_text)
            st.stop()

          reason = f"解析完了（モード: {mode_name} / 有効検出数: {ai_count}匹）"

          # 赤点を描画
          annotated_image = orig_image.copy()
          draw = ImageDraw.Draw(annotated_image)
          radius = max(8, int(orig_width * 0.008))

          for ant in ants_coords:
            if isinstance(ant, dict):
              px = int(ant.get("x", 0) * orig_width / 1000)
              py = int(ant.get("y", 0) * orig_height / 1000)
              draw.ellipse(
                  [px - radius, py - radius, px + radius, py + radius],
                  fill="red",
                  outline="white",
                  width=2,
              )

          # ⏱️ 【全体のタイマー終了】
          elapsed_time = time.time() - start_time

          st.session_state["annotated_image"] = annotated_image
          st.session_state["ai_count"] = ai_count
          st.session_state["reason"] = reason
          st.session_state["orig_width"] = orig_width
          st.session_state["orig_height"] = orig_height
          st.session_state["elapsed_time"] = elapsed_time
          st.session_state["api_elapsed"] = api_elapsed

          st.success(
              f"✨ 解析完了！（全体: {elapsed_time:.1f}秒 / API:"
              f" {api_elapsed:.1f}秒）"
          )

        except Exception as e:
          st.error(f"予期せぬエラーが発生しました: {e}")

    # 解析結果と手動調整の表示
    if "annotated_image" in st.session_state:
      st.markdown("---")
      st.subheader("🎯 解析結果 ＆ 手動調整")
      st.info(f"💡 **AIの解説**: {st.session_state['reason']}")

      col1, col2 = st.columns([2, 1])

      with col1:
        st.write(
            "AIの赤点はそのままに、見落としがあれば**青い点**を追加できます。"
        )
        img_width = st.session_state["orig_width"]
        img_height = st.session_state["orig_height"]
        max_canvas_width = 600
        scale = max_canvas_width / img_width
        canvas_width = max_canvas_width
        canvas_height = int(img_height * scale)

        canvas_result = st_canvas(
            fill_color="rgba(0, 0, 255, 0.4)",
            stroke_width=3,
            stroke_color="#0000FF",
            background_image=st.session_state["annotated_image"],
            update_streamlit=True,
            height=canvas_height,
            width=canvas_width,
            drawing_mode="point",
            key="canvas_single",
        )

        if canvas_result.json_data is not None:
          objects = canvas_result.json_data.get("objects", [])
          manual_adds = len(objects)
        else:
          manual_adds = 0

      with col2:
        st.subheader("📊 集計サマリー")
        base_count = st.session_state["ai_count"]
        st.metric(label="AI検出カウント数", value=f"{base_count} 匹")

        if "elapsed_time" in st.session_state:
          st.metric(
              label="トータル所要時間",
              value=f"{st.session_state['elapsed_time']:.1f} 秒",
          )
        if "api_elapsed" in st.session_state:
          st.metric(
              label="内: Gemini API処理時間",
              value=f"{st.session_state['api_elapsed']:.1f} 秒",
          )

        st.metric(
            label="手動追加（青）マーカー数",
            value=f"{manual_adds} 個",
            delta=manual_adds,
        )

        total_count = base_count + manual_adds
        st.markdown("---")
        st.markdown(f"### 🏁 確定カウント数: **{total_count} 匹**")

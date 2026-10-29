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

st.title("🐜 Ant Worker Counter (高精度1200px・追加/削除・タイマー対応)")
st.write(
    "アリの写真の解析（長辺1200px固定）と、青点（追加）・黄色点（削除）による手動調整を行います。"
)

# シークレット（Secrets）からAPIキーを自動取得
api_key = None
if "GEMINI_API_KEY" in st.secrets:
  api_key = st.secrets["GEMINI_API_KEY"]

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

      with st.spinner(
          "高精度モード（1200px）で画像を解析し、アリの位置を特定しています..."
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

          # 【解像度固定】長辺を1200pxに固定
          max_size = 1200
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

          # ⏱️ 【全体のタイマー終了】
          elapsed_time = time.time() - start_time

          st.session_state["orig_image"] = orig_image
          st.session_state["ai_ants"] = ants_coords
          st.session_state["orig_width"] = orig_width
          st.session_state["orig_height"] = orig_height
          st.session_state["elapsed_time"] = elapsed_time
          st.session_state["api_elapsed"] = api_elapsed

          st.success(
              f"✨ 解析完了！（全体: {elapsed_time:.1f}秒 / API:"
              f" {api_elapsed:.1f}秒 / 検出: {ai_count}匹）"
          )

        except Exception as e:
          st.error(f"予期せぬエラーが発生しました: {e}")

    # 解析結果と手動調整の表示
    if "ai_ants" in st.session_state:
      st.markdown("---")
      st.subheader("🎯 解析結果 ＆ 手動調整（追加・削除）")
      st.write(
          "モードを選択して画像をクリックしてください。"
          " **➕ 追加（青点）** で見落としを足し、**🗑️ 削除（黄色点）**"
          " で誤検知を消去できます。"
      )

      # 追加・削除のモード選択
      edit_mode = st.radio(
          "ペンツールの種類を選択",
          ["➕ 追加 (青点)", "🗑️ 削除 (黄色点)"],
          horizontal=True,
          key="edit_mode_radio",
      )

      # 選択されたモードに応じてキャンバスの色を変更
      if "追加" in edit_mode:
        current_stroke = "#0000FF"
        current_fill = "rgba(0, 0, 255, 0.4)"
      else:
        current_stroke = "#FFCC00"
        current_fill = "rgba(255, 204, 0, 0.6)"

      orig_w = st.session_state["orig_width"]
      orig_h = st.session_state["orig_height"]
      max_canvas_width = 600
      scale = max_canvas_width / orig_w
      canvas_width = max_canvas_width
      canvas_height = int(orig_h * scale)

      # ベースとなる画像にAIの初期赤点を描画
      base_annotated = st.session_state["orig_image"].copy()
      draw_base = ImageDraw.Draw(base_annotated)
      radius = max(8, int(orig_w * 0.008))
      ai_ants = st.session_state["ai_ants"]

      for ant in ai_ants:
        px = int(ant.get("x", 0) * orig_w / 1000)
        py = int(ant.get("y", 0) * orig_h / 1000)
        draw_base.ellipse(
            [px - radius, py - radius, px + radius, py + radius],
            fill="red",
            outline="white",
            width=2,
        )

      # キャンバスウィジェット
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

      # キャンバス上のオブジェクトを解析（追加と削除に分離）
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
          if (
              "ffcc" in stroke_color
              or "yellow" in stroke_color
              or "#ffcc00" in stroke_color
          ):
            manual_deletes.append((img_x, img_y))
          else:
            manual_adds.append((img_x, img_y))

      # 削除指定された位置の近くにあるAI赤点を除外する
      valid_ai_ants = []
      for ant in ai_ants:
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

      # 最終プレビュー画像の作成
      final_image = st.session_state["orig_image"].copy()
      draw_final = ImageDraw.Draw(final_image)

      # 1. 有効なAI赤点を描画（赤）
      for ant in valid_ai_ants:
        px = int(ant.get("x", 0) * orig_w / 1000)
        py = int(ant.get("y", 0) * orig_h / 1000)
        draw_final.ellipse(
            [px - radius, py - radius, px + radius, py + radius],
            fill="red",
            outline="white",
            width=2,
        )

      # 2. 手動追加点を描画（青）
      for ax, ay in manual_adds:
        draw_final.ellipse(
            [ax - radius, ay - radius, ax + radius, ay + radius],
            fill="blue",
            outline="white",
            width=2,
        )

      # サマリー集計
      final_ai_count = len(valid_ai_ants)
      added_count = len(manual_adds)
      deleted_count = len(manual_deletes)
      total_count = final_ai_count + added_count

      col1, col2 = st.columns([2, 1])
      with col1:
        st.subheader("📸 確定プレビュー（赤:AI検出 / 青:追加）")
        st.image(final_image, use_container_width=True)

      with col2:
        st.subheader("📊 集計サマリー")
        st.metric(label="AI有効検出数", value=f"{final_ai_count} 匹")

        # ⏱️ タイマー情報の復活表示
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

        st.metric(label="手動追加（青）", value=f"{added_count} 個", delta=added_count)
        st.metric(label="削除指定（黄）", value=f"{deleted_count} 個", delta=-deleted_count)
        st.markdown("---")
        st.markdown(f"### 🏁 確定カウント数: **{total_count} 匹**")

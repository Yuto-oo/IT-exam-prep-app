# -*- coding: utf-8 -*-
import json
import os
import random
import time
from datetime import datetime
from dotenv import load_dotenv
import streamlit as st

from aws_db import (
    load_user_history_from_aws, 
    load_suspend_state_from_aws, 
    clear_suspend_state_in_aws,
    load_bookmarks_from_aws,
    load_user_profile, # 💡 追加
    save_user_profile  # 💡 追加
)
from dashboard import show_dashboard
from quiz_page import show_quiz_page

load_dotenv()

# --- 🗄️ セッション状態（状態管理）の初期化 ---
if 'user_name' not in st.session_state: st.session_state.user_name = None
if 'exam_code' not in st.session_state: st.session_state.exam_code = None
if 'exam_name' not in st.session_state: st.session_state.exam_name = None
if 'user_level' not in st.session_state: st.session_state.user_level = None
if 'current_index' not in st.session_state: st.session_state.current_index = 0
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'answered' not in st.session_state: st.session_state.answered = False
if 'feedback' not in st.session_state: st.session_state.feedback = ""
if 'score' not in st.session_state: st.session_state.score = 0
if 'finished' not in st.session_state: st.session_state.finished = False
if 'history' not in st.session_state: st.session_state.history = {}
if 'config_done' not in st.session_state: st.session_state.config_done = False
if 'quiz_questions' not in st.session_state: st.session_state.quiz_questions = []
if 'suspended' not in st.session_state: st.session_state.suspended = False
if 'saved_session' not in st.session_state: st.session_state.saved_session = None
if 'bookmarks' not in st.session_state: st.session_state.bookmarks = set()
if 'filter_bm' not in st.session_state: st.session_state.filter_bm = False
if 'is_over_time' not in st.session_state: st.session_state.is_over_time = False 

# 💡 通知設定用のセッション変数を追加
if 'email' not in st.session_state: st.session_state.email = ""
if 'receive_notifications' not in st.session_state: st.session_state.receive_notifications = True

# --- 🛡️ 1. ログイン画面 ---
if st.session_state.user_name is None:
    st.title("🛡️ ログイン")
    with st.form("login_form"):
        input_name = st.text_input("名前 / 学籍番号")
        input_email = st.text_input("メールアドレス（リマインド通知用・任意）") # 💡 追加
        input_level = st.selectbox("現在のあなたの知識レベル", ["初学者（当アプリのみを利用している方）", "中級者（他の勉強アプリ・サイトを同時に利用している方）", "上級者（合格レベル）"])
        input_password = st.text_input("クラス共通パスワード", type="password")
        submit_btn = st.form_submit_button("学習を開始する")
        
        if submit_btn:
            if not input_name: 
                st.warning("⚠️ 名前を入力してください。")
            elif input_password != os.getenv('APP_PASSWORD', 'Exam_Learning'): 
                st.error("❌ パスワードが正しくありません。")
            else:
                st.session_state.user_name = input_name
                st.session_state.user_level = input_level
                st.session_state.exam_name = "基本情報技術者試験A"
                st.session_state.exam_code = "FEA"
                
                with st.spinner("☁️ AWSから過去の学習データと中断データを同期しています..."):
                    # 💡 ユーザープロファイルの同期と保存
                    profile = load_user_profile(input_name)
                    final_email = input_email if input_email else profile.get('email', '')
                    
                    # 初めてメアドを入力した時だけ通知設定をTrueにし、それ以外は前回の設定を引き継ぐ
                    if input_email and not profile.get('email'):
                        final_notif = True
                    else:
                        final_notif = profile.get('receive_notifications', True)
                        
                    save_user_profile(input_name, final_email, final_notif)
                    st.session_state.email = final_email
                    st.session_state.receive_notifications = final_notif

                    st.session_state.history = load_user_history_from_aws(input_name)
                    st.session_state.bookmarks = load_bookmarks_from_aws(input_name)
                    saved_state = load_suspend_state_from_aws(input_name)
                    
                    if saved_state:
                        st.session_state.saved_session = saved_state
                        st.session_state.suspended = True
                    else:
                        st.session_state.saved_session = None
                        st.session_state.suspended = False
                
                st.session_state.config_done = False
                st.rerun()
    st.stop()

# --- 📦 2. ローカルJSONデータロード関数 ---
@st.cache_data
def load_data(exam_code):
    file_map = {"FEA": "FEA5-7_ALL_QA.json", "FEB": "FEB5-7_ALL_QA.json", "IP": "IP3-8_ALL_QA.json"}
    file_name = file_map.get(exam_code)
    if not file_name or not os.path.exists(file_name): return []
    with open(file_name, "r", encoding="utf-8") as f: data = json.load(f)
    
    for q in data:
        opts = q.get("options", {})
        if not opts.get("ア"):
            q_text = q.get("question", "")
            idx_a, idx_i, idx_u, idx_e = q_text.find("ア "), q_text.find("イ "), q_text.find("ウ "), q_text.find("エ ")
            if idx_a != -1 and idx_i != -1 and idx_u != -1 and idx_e != -1:
                q["question"] = q_text[:idx_a].strip()
                q["options"] = {
                    "ア": q_text[idx_a:idx_i].strip().lstrip("ア").strip(),
                    "イ": q_text[idx_i:idx_u].strip().lstrip("イ").strip(),
                    "ウ": q_text[idx_u:idx_e].strip().lstrip("ウ").strip(),
                    "エ": q_text[idx_e:].strip().lstrip("エ").strip()
                }
        orig_type = q.get("question_type", "")
        if "アルゴリズム" in orig_type or "プログラム" in orig_type: q["question_type"] = "アルゴリズム問題"
        elif "計算" in orig_type and "図" in orig_type: q["question_type"] = "図表計算問題"
        elif "計算" in orig_type: q["question_type"] = "計算問題"
        elif "図" in orig_type or "表" in orig_type or "SQL" in orig_type: q["question_type"] = "図表問題"
        else: q["question_type"] = "知識問題"
    return data

questions = load_data(st.session_state.exam_code)

# --- 👤 3. メインサイドバーメニュー ---
st.sidebar.title(f"👤 メニュー")
app_mode = st.sidebar.radio("📋 機能を切り替える", ["クイズ学習", "学習ダッシュボード"])

# 💡 通知設定のコントロールパネルをサイドバーに追加
if st.session_state.user_name:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔔 通知設定")
    st.sidebar.caption("※試験合格後など、リマインド通知を停止したい場合はチェックを外してください。")
    
    current_notif = st.session_state.get('receive_notifications', True)
    new_notif = st.sidebar.checkbox("学習リマインド通知を受け取る", value=current_notif, key="notif_checkbox")
    
    if new_notif != current_notif:
        st.session_state.receive_notifications = new_notif
        save_user_profile(st.session_state.user_name, st.session_state.email, new_notif)
        st.sidebar.success("✅ 通知設定を更新しました")

if st.sidebar.button("ログアウト"): 
    st.session_state.clear()
    st.rerun()

# --- 📊 4. ダッシュボード表示モード ---
if app_mode == "学習ダッシュボード":
    show_dashboard(questions, st.session_state.history, st.session_state.exam_code)
    st.stop()

# --- ⚙️ 5. クイズの出題設定 ---
if not st.session_state.config_done:
    st.title("⚙️ 出題設定")
    
    if st.button("🔄 前回の続きから", use_container_width=True):
        if st.session_state.suspended and st.session_state.saved_session:
            ss = st.session_state.saved_session
            st.session_state.exam_code = ss['exam_code']
            
            exam_options = {"FEA": "基本情報技術者試験A", "FEB": "基本情報技術者試験B", "IP": "ITパスポート"}
            st.session_state.exam_name = exam_options.get(ss['exam_code'], "基本情報技術者試験A")
            
            all_q = load_data(ss['exam_code'])
            
            restored_qs = []
            for sq in ss['q_keys']:
                match = next((q for q in all_q if q.get('year') == sq['year'] and int(q.get('id', 0)) == int(sq['id'])), None)
                if match: restored_qs.append(match)
            
            st.session_state.quiz_questions = restored_qs
            st.session_state.current_index = int(ss['current_index'])
            st.session_state.config_done = True
            st.session_state.is_over_time = False 
            st.session_state.start_time = time.time()
            st.rerun()
        else:
            st.warning("前回の中断ポイントがありません。")

    st.write("---")

    exam_options = {"FEA": "基本情報技術者試験A", "FEB": "基本情報技術者試験B", "IP": "ITパスポート"}
    current_exam_name = exam_options.get(st.session_state.exam_code, "基本情報技術者試験A")
    
    selected_exam_name = st.selectbox("🔍 出題する試験を切り替え", options=list(exam_options.values()), index=list(exam_options.values()).index(current_exam_name), key="quiz_exam_select")
    selected_exam_code = [k for k, v in exam_options.items() if v == selected_exam_name][0]
    
    if selected_exam_code != st.session_state.exam_code:
        st.session_state.exam_code = selected_exam_code
        st.session_state.exam_name = selected_exam_name
        st.session_state.config_done = False
        st.session_state.quiz_questions = []
        st.session_state.current_index = 0
        st.session_state.answered = False
        st.session_state.filter_bm = False
        with st.spinner("☁️ AWSから過去の学習データを同期しています..."):
            st.session_state.history = load_user_history_from_aws(st.session_state.user_name)
        st.rerun()

    st.write("---")

    year_options = sorted(list(set([q["year"] for q in questions if q.get("year")])))
    category_options = sorted(list(set([q["category_large"] for q in questions if q.get("category_large")])))
    
    def format_year_label(y):
        num_str = y.replace('IP', '').replace('FEA', '').replace('FEB', '')
        return f"{num_str}年度"

    col1, col2, col3 = st.columns(3)
    with col1: selected_years = [y for y in year_options if st.checkbox(format_year_label(y), value=True, key=f"y_{y}")]
    with col2: selected_categories = [c for c in category_options if st.checkbox(c, value=True, key=f"c_{c}")]
    with col3: selected_types = [t for t in ["知識問題", "計算問題", "図表問題", "図表計算問題", "アルゴリズム問題"] if st.checkbox(t, value=True, key=f"t_{t}")]

    status_options = ["すべて", "未解答のみ", "要復習（忘却曲線ベースすべて）", "🚨 今すぐ必要", "📅 明日以内", "⏳ 3日以内", "🗓️ 1週間以内", "✅ 安全圏 (1週間以上先)"]
    selected_status = st.selectbox("📊 過去の解答状態・未来予測スケジュールで絞り込む", status_options)
    
    filter_bookmarked = st.checkbox("🔖 ブックマークした問題のみ出題する", key="filter_bm")
    
    selected_order = st.radio("🔀 出題順序", ["順番通り", "ランダム"], horizontal=True)

    temp_filtered = []
    for q in questions:
        check_key = f"{st.session_state.exam_code}_{q.get('year', '不明')}_{q.get('id', 0)}"
        hist = st.session_state.history.get(check_key, {})
        if q.get("year") not in selected_years or q.get("category_large") not in selected_categories or q.get("question_type") not in selected_types: continue
        if selected_status == "未解答のみ" and hist.get('solve_count', 0) > 0: continue
        if selected_status == "要復習（忘却曲線ベースすべて）" and (hist.get('solve_count', 0) == 0 or not hist.get('needs_review', False)): continue
        
        if selected_status in ["🚨 今すぐ必要", "📅 明日以内", "⏳ 3日以内", "🗓️ 1週間以内", "✅ 安全圏 (1週間以上先)"]:
            if hist.get('solve_count', 0) == 0: continue
            days = hist.get('days_until_review', 0.0)
            if days <= 0: current_sched_group = "🚨 今すぐ必要"
            elif days <= 1: current_sched_group = "📅 明日以内"
            elif days <= 3: current_sched_group = "⏳ 3日以内"
            elif days <= 7: current_sched_group = "🗓️ 1週間以内"
            else: current_sched_group = "✅ 安全圏 (1週間以上先)"
            if selected_status != current_sched_group: continue
            
        if filter_bookmarked and check_key not in st.session_state.bookmarks:
            continue
            
        temp_filtered.append(q)

    if temp_filtered:
        total_count = len(temp_filtered)
        
        if total_count == 1:
            st.info("ℹ️ 該当する問題が 1 件のみのため、1問に設定されました。")
            max_questions = 1
        else:
            max_questions = st.slider("出題問題数", 1, total_count, total_count)
            
        if st.button("クイズを開始する 🚀", type="primary", use_container_width=True):
            if selected_order == "ランダム": random.shuffle(temp_filtered)
            st.session_state.quiz_questions = temp_filtered[:max_questions]
            st.session_state.config_done = True
            st.session_state.current_index = 0
            st.session_state.score = 0
            st.session_state.answered = False
            
            st.session_state.suspended = False
            st.session_state.saved_session = None
            st.session_state.is_over_time = False 
            clear_suspend_state_in_aws(st.session_state.user_name)
            
            st.session_state.start_time = time.time()
            st.rerun()
    else:
        st.warning("⚠️ 選択した条件に合致する問題がありません。絞り込みを緩めてください。")
        
    st.write("---")
    st.caption("※ 本アプリの問題文・解答例はIPA（情報処理推進機構）の公表資料を利用しています。  \n※ 解説文はLLM（AI）により自動生成された独自コンテンツです。")
    
    st.stop()

# --- 🎊 6. クイズの全問終了画面 ---
if st.session_state.finished:
    st.title("🎊 学習完了！")
    st.markdown(f"### 今回の成果: **{st.session_state.score} / {len(st.session_state.quiz_questions)}** 問正解")
    if st.button("トップへ戻り、もう一度設定する", use_container_width=True, type="primary"): 
        st.session_state.config_done = False
        st.session_state.finished = False
        st.session_state.quiz_questions = []
        
        st.session_state.suspended = False
        st.session_state.saved_session = None
        st.session_state.is_over_time = False 
        clear_suspend_state_in_aws(st.session_state.user_name)
        
        st.rerun()
    st.stop()

# --- 📝 7. クイズ学習画面 ---
if st.session_state.config_done and not st.session_state.finished:
    if st.session_state.current_index >= len(st.session_state.quiz_questions):
        st.session_state.finished = True
        st.rerun()
    else:
        current_q = st.session_state.quiz_questions[st.session_state.current_index]
        show_quiz_page(current_q)
import datetime
import chains
import time
import streamlit as st

def set_chat_message(role, content, references=None):
    if role == 'ai':
        with st.chat_message("ai"):
            placeholder = st.empty()
            text = ""
            for char in content:
                text += char
                placeholder.markdown(text)
                time.sleep(0.02)
    else:
        with st.chat_message(role):
            st.write(content)

    st.session_state['history'].append({
        "role":role,
        "content":content,
        "references": references
    })

def write_history():
    for message in st.session_state['history']:
        with st.chat_message(message['role']):
            st.write(message['content'])

# 初始化 session_state
if 'history' not in st.session_state:
    st.session_state['history'] = []

#-------------------- main page --------------------
# 設定頁面
st.set_page_config(page_title="醫療機器人")
write_history()
# Sidebar
with st.sidebar:
    st.header('基本資料')

    # 姓名
    name = st.text_input(
        "姓名",
        value=st.session_state.get("name", ""),
        key="name"
    )

    # 出生年月日
    birthday = st.date_input(
        "出生年月日",
        value=st.session_state.get("birthday", datetime.date.today()),
        key="birthday"
    )

    # 血型
    blood_types = ["A", "B", "AB", "O"]
    blood_type_default = st.session_state.get("blood_type", "A")
    blood_type = st.selectbox(
        "血型",
        blood_types,
        index=blood_types.index(blood_type_default),
        key="blood_type"
    )

    st.markdown("---")
    st.write("這裡是 Sidebar 區域")

# 主頁面
st.title("醫療機器人 Demo")
st.write("主頁面可以顯示對話或其他內容。")
if question := st.chat_input("請輸入您的訊息"):
    with st.chat_message("user"):
        st.write(question)
    
    if not all([name, birthday, blood_type]):
        with st.chat_message("ai"):
            st.write("請先填寫基本資料")
            
    else:
        #with st.chat_message("ai"):
        #    #st.write("WIP")
        #    suggestion = chains.get_suggestion_chain(question)
        #    st.write(suggestion.get("result"))
        try:
           profile_text = f"姓名: {name}, 出生年月日: {birthday.strftime('%Y-%m-%d')}, 血型: {blood_type}"
           suggestion = chains.get_suggestion_chain(question, profile_text)
           #print('++++++')
           #print(type(suggestion),suggestion)
           #print('++++++')
           set_chat_message(
               "ai",
               suggestion.get("answer"),
               [
                    {
                        "id": doc.metadata.get("_id"),
                        "department": doc.metadata.get("department"),
                        "symptom": doc.metadata.get("symptom"),
                        "answer": doc.metadata.get("answer"),
                        "question": doc.page_content,
                    }
                    for doc in suggestion.get("context", [])
                ]
           )
        except Exception as e:
          print(e)
          set_chat_message(
              "ai",
              "很抱歉 寫我的工程師是個笨蛋 她剛剛在中山大學被猴子咬了"
          ) 

if st.session_state['history'] and not st.session_state['history'][-1]['content'] == "請先填寫基本資料，再進行問答！":
    with st.expander("📋 問診結果"):
        st.subheader("👤 使用者資料")
        st.write(f"**姓名**：{name or '（未填寫）'}")
        st.write(f"**出生年月日**：{birthday.strftime('%Y-%m-%d')}")
        st.write(f"**血型**：{blood_type}")

        st.subheader("💬 問診對話")
        for msg in st.session_state['history'][-2:]:
            speaker = "使用者" if msg['role'] == "user" else "機器人"
            st.markdown(f"**{speaker}：** {msg['content']}")

        if st.session_state['history'][-1].get('references'):
            st.subheader("📑 參考資料")
            for reference in st.session_state['history'][-1]['references']:
                st.markdown(f"- **症狀分類**：{reference['department']} / {reference['symptom']}")
                st.markdown(f"- **患者主訴**：")
                st.markdown(f"{reference['question']}")
                st.markdown(f"- **醫師回覆**：")
                st.markdown(f"{reference['answer'].replace('回覆', '')}")
                st.write("---")
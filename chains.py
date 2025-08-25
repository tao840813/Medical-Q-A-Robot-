import os
import pathlib
import tomlkit
import contextlib
import asyncio
import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient
from langchain_openai import ChatOpenAI
from langchain_mongodb.vectorstores import MongoDBAtlasVectorSearch
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.memory import ConversationBufferMemory
from pprint import pprint

# ---------------- MongoDB 設定 ----------------
secret_file = pathlib.Path.cwd() / ".streamlit" / "secrets.toml"
with open(secret_file, "r", encoding="utf-8") as f:
    config = tomlkit.parse(f.read())
os.environ["MONGODB_ATLAS_CLUSTER_URI"] = config["MONGODB_ATLAS_CLUSTER_URI"]
os.environ["GOOGLE_API_KEY"] = config["GOOGLE_API_KEY"]
client = MongoClient(os.getenv("MONGODB_ATLAS_CLUSTER_URI"))
db = client["MediGuide"]
collection = db["Symptom"]

@st.cache_resource
def get_embedding():
    """
    Problem
    Python 的異步編程依賴於事件循環（Event Loop）
    每個執行緒通常只能有一個事件循環

    Streamlit(MainThread) -> streamlit服務
                          -> ScriptRunner.scriptThread #<-自己寫的程式碼在這邊執行
                                                        <- googleGenerativeAIEmbeddings使用了異步客戶端
                                                        <- asyncio.get_event_loop() 在streeamlit裡面找不到循環
    簡單來說就是ScriptRunner.scriptThread需要embedding但是Streamlit沒有
    Sol:
        @st.cache_resource  -> 讓裝飾的函數在主執行緒中進行(不在ScriptRunner.scriptThread)
        構建embedding在MainThread, 如果runner需要的話從快取去調度就可以
        也避免重複建構embedding的問題

    """
    try:
        loop = asyncio.get_event_loop()
        """
        # 執行流程：
            第一次調用 get_embedding()
            ├── Streamlit 在適當的執行緒中執行函數
            ├── 建立事件循環（如果需要）
            ├── 初始化 GoogleGenerativeAIEmbeddings
            ├── 快取結果
            └── 回傳給 ScriptRunner.scriptThread

            後續調用 get_embedding()
            └── 直接回傳快取的結果（不重新初始化）
        """
    except RuntimeError:
        loop = asyncio.new_event_loop() # 建立新的事件循環
        asyncio.set_event_loop(loop) # 設置為當前執行緒的事件循環
    return GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

@contextlib.contextmanager
def get_mongo_vectorstore() -> MongoDBAtlasVectorSearch:
    embedding = get_embedding() # 延遲初始化
    vectorstore = MongoDBAtlasVectorSearch(
        collection=collection,
        embedding=embedding,
        index_name='default',
        embedding_key="question_embeddings",
        text_key="question"
    )
    yield vectorstore

# ---------------- LLM 初始化 ----------------
load_dotenv()
llm = ChatOpenAI(
    model="gemini-2.5-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url=os.getenv("GEMINI_BASE_URL")
)

# ---------------- 記憶體 ----------------
memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True
)

# ---------------- 主功能 ----------------
def get_suggestion_chain(question: str):
    with get_mongo_vectorstore() as vectorstore:
        retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 3})

        # 1️⃣ 建立「上下文重寫」retriever
        contextualize_q_prompt = ChatPromptTemplate.from_messages([
            ("system", "你是一個醫療助理，請根據對話歷史，將使用者的追問改寫成完整問題。"),
            ("human", "{input}")
        ])
        history_aware_retriever = create_history_aware_retriever(
            llm, retriever, contextualize_q_prompt
        )

        # 2️⃣ 建立 QA prompt
        qa_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "你是一個專業的醫生。\n"
             "以下是過去的對話紀錄：{chat_history}\n\n"
             "參考資料：{context}\n\n"
             "請根據上下文與參考資料，用繁體中文提供簡短建議（≤300字）。"
             "如果患者說了很明顯是誇大的情況，請用日本搞笑藝人的方式吐槽，但吐槽完後還是認真地給予建議。"
             "如果患者說了和症狀 疾病等醫學資訊無關的問題，請用粗魯的語氣叫他閉嘴。"
             ),
            ("human", "{input}")
        ])
        document_chain = create_stuff_documents_chain(llm, qa_prompt)

        # 3️⃣ 建立檢索 QA chain
        qa_chain = create_retrieval_chain(history_aware_retriever, document_chain)

        # 4️⃣ 執行查詢
        result = qa_chain.invoke({
            "input": question,
            "chat_history": memory.load_memory_variables({})["chat_history"]
        })

        # 5️⃣ 更新記憶
        memory.save_context({"input": question}, {"output": result["answer"]})

        print("=== 答案 ===")
        print(result["answer"])
        print("=== 來源文件 ===")
        pprint(result.get("context", []))

        return result

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
from asyncio import Queue

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import ChatOllama
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain_core.callbacks import BaseCallbackHandler

# --- Async streaming handler ---
class StreamHandler(BaseCallbackHandler):
    def __init__(self):
        self.queue = Queue()

    def on_llm_new_token(self, token: str, **kwargs):
        self.queue.put_nowait(token)

    async def get_stream(self):
        while True:
            token = await self.queue.get()
            if token is None:
                break
            yield token

# --- FastAPI app ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000","https://astitvabhate.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Load FAISS vector store ---
embedding = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
db = FAISS.load_local("faiss_index", embedding, allow_dangerous_deserialization=True)

# --- Request model ---
class Question(BaseModel):
    query: str

# --- Streaming endpoint ---
@app.post("/ask")
async def ask(question: Question):
    handler = StreamHandler()
    llm = ChatOllama(
        model="mistral",
        stream=True,
        callbacks=[handler],
        temperature=0.3
    )

    prompt = PromptTemplate(
        input_variables=["context", "question"],
        template="""
        Answer the following question based on the provided context.
        Use Markdown for formatting (e.g., *bold*, bullet points, links).
        Add navigation using [Section Name](#section-name).
        
        Context:
        {context}
        
        Question:
        {question}
        """
    )

    qa = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=db.as_retriever(),
        chain_type="stuff",
        chain_type_kwargs={"prompt": prompt},
    )

    asyncio.create_task(qa.ainvoke({"query": question.query}))
    return StreamingResponse(handler.get_stream(), media_type="text/plain")

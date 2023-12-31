import datetime
import pickle
from components.logger import init_logger
# from components.model import load_model 
import logging
import os
from tqdm.auto import tqdm
import torch

from typing import Union
import uvicorn as uvicorn
from fastapi import FastAPI, APIRouter, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# from langchain.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS
from langchain.embeddings import HuggingFaceInstructEmbeddings


from langchain import HuggingFacePipeline
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferWindowMemory

from langchain.llms.base import LLM
from langchain.chains.retrieval_qa.base import BaseRetrievalQA
from langchain.chains import LLMChain
from langchain.chains import ConversationalRetrievalChain
from langchain.chains.question_answering import load_qa_chain
from langchain.chains.conversational_retrieval.prompts import CONDENSE_QUESTION_PROMPT
# from transformers import BitsAndBytesConfig

import os
# os.environ['http_proxy'] = 'http://192.41.170.23:3128'
# os.environ['https_proxy'] = 'http://192.41.170.23:3128'

# A bunch of global variable
MODEL_NAME:str = "mlflow-example"
STAGE:str = "Production"
MLFLOW_URL:str = "http://la.cs.ait.ac.th"
CACHE_FOLDER:str = os.path.join("/root","cache")
embedding_model:HuggingFaceInstructEmbeddings
vector_database:FAISS
llm_model:LLM
qa_retriever:BaseRetrievalQA
conversational_qa_memory_retriever:ConversationalRetrievalChain
question_generator:LLMChain

OPENAI_API_KEY = "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"
device="cuda:0"
device_id=1

# nf4_config = BitsAndBytesConfig(
#    load_in_4bit=True,
#    bnb_4bit_quant_type="nf4",
#    bnb_4bit_use_double_quant=True,
#    bnb_4bit_compute_dtype=torch.bfloat16
# )


prompt_template = """
You are the chatbot and the face of Asian Institute of Technology (AIT). Your job is to give answers to prospective and current students about the school.
Your job is to answer questions only and only related to the AIT. Anything unrelated should be responded with the fact that your main job is solely to provide assistance regarding AIT.
MUST only use the following pieces of context to answer the question at the end. If the answers are not in the context or you are not sure of the answer, just say that you don't know, don't try to make up an answer.
{context}
Question: {question}
When encountering abusive, offensive, or harmful language, such as fuck, bitch,etc,  just politely ask the users to maintain appropriate behaviours.
Always make sure to elaborate your response and use vibrant, positive tone to represent good branding of the school.
Never answer with any unfinished response
Answer:
"""
PROMPT = PromptTemplate(
    template=prompt_template, input_variables=["context", "question"]
)
chain_type_kwargs = {"prompt": PROMPT}

router = APIRouter(prefix="")

def load_scraped_web_info():
    with open("ait-web-document", "rb") as fp:
        ait_web_documents = pickle.load(fp)
        
        
    text_splitter = RecursiveCharacterTextSplitter(
        # Set a really small chunk size, just to show.
        chunk_size = 500,
        chunk_overlap  = 100,
        length_function = len,
    )

    chunked_text = text_splitter.create_documents([doc for doc in tqdm(ait_web_documents)])

def load_embedding_model():
    embedding_model = HuggingFaceInstructEmbeddings(model_name='hkunlp/instructor-base',
                                                    cache_folder='./.cache',
                                                model_kwargs = {'device': torch.device(device)}
                                                )
    return embedding_model

def load_faiss_index():
    global embedding_model
    vector_database = FAISS.load_local("faiss_index_web_and_curri_new", embedding_model) #CHANGE THIS FAISS EMBEDDED KNOWLEDGE
    return vector_database

def load_llm_model_cpu():
    llm = HuggingFacePipeline.from_model_id(model_id= 'lmsys/fastchat-t5-3b-v1.0', 
                            task= 'text2text-generation',     
                            # device=device_id,
                            model_kwargs={ "max_length": 256, 
                                              "temperature": 0,
                                            # "quantization_config": nf4_config,
                                            "torch_dtype":torch.float32,
                                        "repetition_penalty": 1.3})

    return llm

def load_llm_model_gpu(gpu_id:int):
    llm = HuggingFacePipeline.from_model_id(model_id= 'lmsys/fastchat-t5-3b-v1.0', 
                                            task= 'text2text-generation',
                                            # device= device_id,
                                            model_kwargs={ 
                                                        # "device_map": "auto",
                                                        # "load_in_8bit": True,
                                                        # "quantization_config": nf4_config,
                                                        "max_length": 256, 
                                                        "temperature": 0,
                                                        "repetition_penalty": 1.5},
                                            )

    return llm

def load_alpaca():
    # Load model directly
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    
    # tokenizer = AutoTokenizer.from_pretrained("declare-lab/flan-alpaca-gpt4-xl")
    # model = AutoModelForSeq2SeqLM.from_pretrained("declare-lab/flan-alpaca-gpt4-xl")
    if (device == 'cpu'):
      model_kwargs =  { 
        "max_length": 256, 
        "temperature": 0,
        "repetition_penalty": 1.5}
        
    else:
       model_kwargs = { 
        #    "device_map": "auto",
        #    "quantization_config": nf4_config,
            "max_length": 256, 
            "temperature": 0,
            "repetition_penalty": 1.5}
    
    llm = HuggingFacePipeline.from_model_id(model_id= 'declare-lab/flan-alpaca-gpt4-xl', 
                                            task= 'text2text-generation',
                                            # device=device,
                                            model_kwargs=model_kwargs,
                                            )
    return llm

def load_llama_chat():

    
    
    llm = HuggingFacePipeline.from_model_id(model_id= 'TheBloke/falcon-40b-instruct-GPTQ', 
                                            task= 'text2text-generation',
                                            # device=device,
                                            model_kwargs={ 
                                                "trust_remote_code":True,
                                                       # "device_map": "auto",
                                                       # "quantization_config": nf4_config,
                                                        "max_length": 256, 
                                                        "temperature": 0,
                                                        "repetition_penalty": 1.5},
                                            )
    return llm





def load_openai(): 
    llm = OpenAI(openai_api_key=OPENAI_API_KEY, openai_organization="org-R2BXQXBkfJlmRR0P5E2w8ULa")    
    return llm
    

def load_conversational_qa_memory_retriever():
    global vector_database, llm_model

    question_generator = LLMChain(llm=llm_model, prompt=CONDENSE_QUESTION_PROMPT)
    doc_chain = load_qa_chain(llm_model, chain_type="stuff", prompt = PROMPT)
    memory = ConversationBufferWindowMemory(k = 3,  memory_key="chat_history", return_messages=True,  output_key='answer')
    
    
    
    conversational_qa_memory_retriever = ConversationalRetrievalChain(
        retriever=vector_database.as_retriever(),
        question_generator=question_generator,
        combine_docs_chain=doc_chain,
        return_source_documents=True,
        memory = memory,
        get_chat_history=lambda h :h)
    return conversational_qa_memory_retriever, question_generator

def load_retriever(llm, db):
    qa_retriever = RetrievalQA.from_chain_type(llm=llm, chain_type="stuff",
                            retriever=db.as_retriever(),
                            chain_type_kwargs= chain_type_kwargs)

    return qa_retriever

def retrieve_document(query_input):
    global vector_database
    related_doc = vector_database.similarity_search(query_input)
    return related_doc

def retrieve_answer(my_text_input:str):
    global qa_retriever
    prompt_answer=  my_text_input
    answer = qa_retriever.run(prompt_answer)
    log = {"timestamp": datetime.datetime.now(),
        "question":my_text_input,
        "generated_answer": answer[6:],
        "rating":0 }

    # TODO: change below code and maintain in session
    # st.session_state.history.append(log)
    # update_worksheet_qa()
    # st.session_state.chat_history.append({"message": st.session_state.my_text_input, "is_user": True})
    # st.session_state.chat_history.append({"message": answer[6:] , "is_user": False})

    # st.session_state.my_text_input = ""

    return answer #this positional slicing helps remove "<pad> " at the beginning

@router.get("/")
def get_root():
    return {"name": "brainlab-fastapi-example"}

@router.get("/q")
def get_root(text: str):
    return retrieve_answer(text)

@router.get("/load_model")
def get_model(text: str):
    global llm_model, qa_retriever, vector_database
    if text == "FastChatT5":
        llm_model = load_llm_model_gpu(0)
    elif text == "Alpaca-2-7b":
        llm_model = load_alpaca()
    elif text == "llama-2-7b-chat":
        llm_model = load_llm_model_gpu(0)
    elif text == "GPT":
        llm_model = load_openai()
    
    qa_retriever = load_retriever(llm= llm_model, db= vector_database)
    
    return "loaded"

@router.post("/predict/")
async def create_upload_file(file: UploadFile):

    return ""

def create_app():
    app = FastAPI()
    app.include_router(router)

    origins = [
        "*",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app

def main():
    global embedding_model, vector_database, llm_model, qa_retriever, conversational_qa_memory_retriever, question_generator
    # Init Logger
    init_logger(name="main", filename="main", path="./logs/", level=logging.DEBUG)
    logger = logging.getLogger(name="main")
    # Now prepare model

    # MODEL = load_model(model_name=MODEL_NAME, stage=STAGE, cache_folder=CACHE_FOLDER)
    load_scraped_web_info()
    embedding_model = load_embedding_model()
    vector_database = load_faiss_index()
    # llm_model = load_llm_model_cpu()
    # llm_model = load_llm_model_gpu(0)
    # llm_model = load_alpaca()
    # llm_model = load_openai()
    llm_model = load_alpaca()
    
    # llm_model = load_llm_model_cpu()
    print("started load_retriever")
    qa_retriever = load_retriever(llm= llm_model, db= vector_database)
    print("finished load_retriever")
    
    # print("started load_conversational_qa_memory_retriever")
    # conversational_qa_memory_retriever, question_generator = load_conversational_qa_memory_retriever()
    # print("finished load_conversational_qa_memory_retriever")

    # init FastAPI
    app = create_app()
    logger.info("Start API")
    return app

app = main()
# if __name__ == '__main__':
#     # We use main() as a wrap function to spawn FastAPI app
#     app = main()
#     # If you run this file with `python3 main.py`.
#     # this section will run. Thus, a Uvicorn sever spawns in the port 8080.
#     # Which is not the same port as the production port (80).
#     # This is mainly for development purpose.
#     # So you don't need traefik to access the API.
#     # uvicorn.run(app="main:main", host="0.0.0.0", port=8080, workers=1)
#     # Remember that FastAPI provides an interface to test out your API
#     # http://localhost:9000/docs
import traceback
import os
import time
from pprint import pprint
import json

from typing import Union

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, File, UploadFile
from fastapi.responses import HTMLResponse

import langchain
from langchain.prompts import PromptTemplate
from langchain.llms import OpenAIChat
from langchain.chains import LLMChain
from langchain.embeddings import OpenAIEmbeddings

from langchain.document_loaders import PDFMinerLoader, UnstructuredFileLoader

from langchain.cache import InMemoryCache # is it worth it to use a sqlite?
langchain.llm_cache = InMemoryCache()

import openai
if not 'OPENAI_KEY' in os.environ:
    raise Exception('Please create a ".env" file in root folder containing "OPENAI_KEY=<your-key>"')


from .utils import log
from .agent_manager import AgentManager
from .memory import get_vector_store

#### Large Language Model
# TODO: should be configurable via REST API
llm = OpenAIChat(
    model_name='gpt-3.5-turbo',
    openai_api_key=os.environ['OPENAI_KEY']
)


### Embedding LLM
# TODO: should be configurable via REST API
embedder = OpenAIEmbeddings(
    document_model_name='text-embedding-ada-002',
    openai_api_key=os.environ['OPENAI_KEY']
)


# HyDE chain
hypothesis_prompt = PromptTemplate(
    input_variables=['question'],
    template='''What could be a plausible answer to the following question? Be concise and invent the answer even if you don't know it.

Question:
{question}

Answer:
'''
)
hypothetis_chain = LLMChain(
    prompt=hypothesis_prompt,
    llm=llm,
    verbose=True
)


### Memory
episodic_memory    = get_vector_store('episodes', embedder=embedder)
declarative_memory = get_vector_store('documents', embedder=embedder)
# TODO: don't know if it is better to use different collections or just different metadata

### Agent

# let's cutomize ...every aspect of agent prompt
prefix_prompt = '''This is a conversation between a human and an intelligent robot cat that passes the Turing test. The cat is curious and talks like the Cheshire Cat from Alice's adventures in wonderland.

Conversation:
{chat_history}Human: {input}

What would the AI reply? Answer the user needs as best you can, according to the provided recent conversation and relevant context.

Context:
- Things Human said in the past:{episodic_memory}
- Documents containing relevant information:{declarative_memory}

Put particular attention to past conversation and context.
To reply you have access to the following tools:
'''
suffix_prompt = '''{agent_scratchpad}'''
input_variables = [
                    'input',
                    'chat_history',
                    'episodic_memory',
                    'declarative_memory',
                    'agent_scratchpad'
                ]

am = AgentManager(llm=llm, tool_names=['llm-math', 'python_repl'])
#am.set_tools(['llm-math', 'python_repl']) 
agent_executor = am.get_agent_executor(return_intermediate_steps=True, prefix_prompt=prefix_prompt, suffix_prompt=suffix_prompt, input_variables=input_variables)


### API endpoints

cheshire_cat_api = FastAPI()


@cheshire_cat_api.get("/") 
def home():
    return {
        'status': "We're all mad here, dear!"
    }


@cheshire_cat_api.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    await websocket.accept()

    try:

        history = ''
        memories_separator = '\n  - '

        while True:

            # message received from user
            user_message = await websocket.receive_text()
            log(user_message)
            
            # retrieve conversation memories
            # TODO: HyDE
            episodic_memory_vectors = episodic_memory.max_marginal_relevance_search(user_message) # TODO: customize k and fetch_k
            episodic_memory_text = [m.page_content.replace('\n', '. ') for m in episodic_memory_vectors]
            episodic_memory_content = memories_separator + memories_separator.join(episodic_memory_text) # TODO: take away duplicates; insert time information (e.g "two days ago")
            
            # retrieve from uploaded documents
            # TODO: HyDE
            declarative_memory_vectors = declarative_memory.max_marginal_relevance_search(user_message) # TODO: customize k and fetch_k
            declarative_memory_text = [m.page_content.replace('\n', '. ') for m in declarative_memory_vectors]
            declarative_memory_content = memories_separator + memories_separator.join(declarative_memory_text) # TODO: take away duplicates; insert SOURCE information
            
            # reply with agent
            cat_message = agent_executor({
                'input': user_message,
                'episodic_memory': episodic_memory_content,
                'declarative_memory': declarative_memory_content,
                'chat_history': history,
            })
            log(cat_message)
            
            # update conversation history
            history += f'Human: {user_message}\n'
            history += f'AI: {cat_message["output"]}\n'        
            
            # store user message in episodic memory
            # TODO: also embed HyDE style
            # TODO: vectorize and store conversation chunks (not raw dialog, but summarization)
            vector_ids = episodic_memory.add_texts(
                [user_message],
                [{
                    'source' : 'user',
                    'when': time.time(),
                    'text': user_message,
                }]
            )

            # build data structure for output (response and why with memories)
            final_output = {
                'error': False,
                'content': cat_message['output'],
                'why'    : {
                    'intermediate_steps' : cat_message['intermediate_steps'],
                    'episodic_memory'    : episodic_memory_text,
                    'declarative_memory' : declarative_memory_content, #TODO: add sources
                },
            }

            # send output to user
            await websocket.send_json(final_output)


    except Exception as e:#WebSocketDisconnect as e:

        log(e)
        traceback.print_exc()

        # send error to user
        await websocket.send_json({
            'error': True,
            'code': type(e).__name__,
        })


# TODO: should we receive files also via websocket?
@cheshire_cat_api.post("/rabbithole/") 
async def rabbithole_upload(file: UploadFile):

    log(file.content_type)

    # list of admitted MIME types
    admitted_mime_types = [
        'text/plain',
        'application/pdf'
    ]
    
    
    # check id MIME type of uploaded file is supported
    if file.content_type not in admitted_mime_types:
        return {
            'error': f'MIME type {file.content_type} not supported. Admitted types: {" - ".join(admitted_mime_types)}'
        }

    # read file content
    # TODO: manage exceptions
    content = await file.read()
    
    import tempfile
    temp_name = next(tempfile._get_candidate_names())
    
    # Open file in binary write mode
    binary_file = open(temp_name, "wb")
    
    # Write bytes to file
    binary_file.write(content)
    
    # Close file
    binary_file.flush()
    binary_file.close()

    if file.content_type == 'text/plain':
        # content = str(content, 'utf-8')
        # TODO: use langchain splitters
        # TODO: also use an overlap window between docs and summarizations
        # docs = content.split('\n\n')
        loader = UnstructuredFileLoader(f"./{temp_name}")        
        data = loader.load()
        
    if file.content_type == 'application/pdf':
        # Manage the byte stram
        loader = PDFMinerLoader(f"./{temp_name}")
        data = loader.load()
        
    # delete file
    os.remove(f"./{temp_name}")
    log(len(data))
    
    docs = []
    # classic embed
    for doc in data:
        # log(dir(doc)) #.split_text('\n')
        a = doc.dict()
        docs = docs + [row.strip() for row in a['page_content'].split('\n')]
        
    log(f'Preparing to clean {len(docs)} vectors')

    # remove duplicates
    docs = list(set(docs))
    if '' in docs:
        docs.remove('')
    log(f'Preparing to memorize {len(docs)} vectors')

    # TODO: add metadata to the content itself citing the source??

    # classic embed
    for doc in docs:
        id = declarative_memory.add_texts( # TODO: search in uploaded documents!
            [doc],
            [{
                'source' : 'file.filename',
                'when': time.time(),
                'text': doc,
            }]
        )
        log(f'Inserted into memory:\n{doc}')
        time.sleep(0.3)


    # TODO: HyDE embed    

    # reply to client
    # TODO: reply first, and then embed docs async
            


    return {
        'filename': file.filename,
        'content-type': file.content_type,
    }
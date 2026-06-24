# 🧠 Short-Term Memory Chatbot — Detailed Workflow

> **File:** `short_term_memory.py`  
> **Framework:** LangGraph + LangChain + Groq (LLaMA 3.3 70B)  
> **Purpose:** A conversational chatbot with short-term (in-session) memory using LangGraph's checkpointing system.

---

## 📦 1. Imports & Dependencies

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import AnyMessage, SystemMessage, AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from dotenv import load_dotenv
import os
import uuid
import operator
from typing_extensions import TypedDict, Annotated

from langchain_groq import ChatGroq
```

| Import | Purpose |
|--------|---------|
| `StateGraph, START, END` | Core LangGraph classes to define a directed computation graph |
| `InMemorySaver` | In-process checkpointer that stores conversation state in RAM |
| `AnyMessage, AIMessage, HumanMessage` | LangChain message types to distinguish user vs. AI messages |
| `ChatPromptTemplate, MessagesPlaceholder` | Builds structured prompts with dynamic message injection |
| `load_dotenv` | Loads `GROQ_API_KEY` from the `.env` file |
| `uuid` | Generates a unique session ID per run |
| `operator` | Used with `Annotated` to define how message lists are merged |
| `TypedDict, Annotated` | Type-safe state schema for the graph |
| `ChatGroq` | LangChain wrapper for the Groq inference API |

---

## 🔐 2. Environment Setup & LLM Initialization

```python
load_dotenv()

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0
)
```

- **`load_dotenv()`** — reads the `.env` file and exposes `GROQ_API_KEY` as an environment variable so the Groq client can authenticate.
- **`ChatGroq`** — creates a client connected to Groq's API.
  - `model="llama-3.3-70b-versatile"` — uses Meta's LLaMA 3.3 70B model, a powerful instruction-following model.
  - `temperature=0` — deterministic output; the model always picks the highest-probability token (no randomness).

---

## 🔗 3. Prompt Template & Chain (Module Level)

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", """You are Jarvis, a helpful AI assistant. Use conversation memory properly 
                  and answer based on the previous messages."""),
    MessagesPlaceholder(variable_name="messages")
])

chain = prompt | llm
```

- **`ChatPromptTemplate.from_messages`** — builds a reusable prompt structure with two parts:
  1. **System message** — sets the AI persona ("Jarvis") and instructs it to use conversation history.
  2. **`MessagesPlaceholder`** — a dynamic slot that gets filled with the full message history at runtime.

- **`chain = prompt | llm`** — uses the LangChain pipe (`|`) operator to compose a chain:
  - First the prompt formats the input → then passes it to the LLM.
  - Defined **once at module level** (not inside the node function) so it is not rebuilt on every chat turn, saving overhead.

---

## 🗂️ 4. State Schema — `MessageState`

```python
class MessageState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int
```

This is the **shared state** that flows through the LangGraph graph.

| Field | Type | Description |
|-------|------|-------------|
| `messages` | `list[AnyMessage]` | Full conversation history (both user and AI messages) |
| `llm_calls` | `int` | Running count of how many times the LLM has been called this session |

- **`Annotated[list[AnyMessage], operator.add]`** — the `operator.add` reducer tells LangGraph to **append** new messages to the existing list rather than overwriting it. This is what enables memory: every new message is accumulated.

---

## 🤖 5. Chatbot Node Function

```python
def chatbot_node(state: MessageState):
    try:
        response = chain.invoke({"messages": state["messages"]})
    except Exception as e:
        response = AIMessage(content=f"Sorry, I encountered an error: {e}")

    return {
        "messages": [response],
        "llm_calls": state["llm_calls"] + 1
    }
```

This is the **only node** in the graph. It runs every time the user sends a message.

### Step-by-step inside the node:

1. **`chain.invoke({"messages": state["messages"]})`**
   - Passes the **entire conversation history** (`state["messages"]`) into the prompt template.
   - The `MessagesPlaceholder` expands it into the full message list.
   - The LLM receives context of all previous turns, enabling it to "remember" prior exchanges.

2. **`try / except`**
   - If the Groq API throws any exception (rate limit, network error, timeout), the error is caught and a friendly `AIMessage` is returned instead of crashing.

3. **Return value**
   - `"messages": [response]` — the new AI response is returned as a single-item list. LangGraph's `operator.add` reducer appends it to the existing history.
   - `"llm_calls": state["llm_calls"] + 1` — increments the call counter by 1.

---

## 🏗️ 6. Graph Construction

```python
builder = StateGraph(MessageState)
builder.add_node("chatbot", chatbot_node)
builder.add_edge(START, "chatbot")
builder.add_edge("chatbot", END)
```

- **`StateGraph(MessageState)`** — creates a directed graph whose nodes share `MessageState`.
- **`add_node("chatbot", chatbot_node)`** — registers the `chatbot_node` function as a graph node named `"chatbot"`.
- **`add_edge(START, "chatbot")`** — execution always begins at the `chatbot` node.
- **`add_edge("chatbot", END)`** — after `chatbot_node` completes, execution ends.

### Graph Topology:

```
START ──► chatbot ──► END
```

A simple linear graph — one node, no branching.

---

## 💾 7. Memory (Checkpointing) & Compilation

```python
memory = InMemorySaver()
app = builder.compile(checkpointer=memory)
```

- **`InMemorySaver()`** — a checkpointer that stores the full graph state (including the entire `messages` list) in RAM, keyed by `thread_id`.
- **`builder.compile(checkpointer=memory)`** — compiles the graph into a runnable `app` and attaches the memory backend.
  - On each `app.stream(...)` call, LangGraph:
    1. **Loads** the previous state snapshot for the given `thread_id`.
    2. **Runs** the node.
    3. **Saves** the new state snapshot back.
  - This is how conversation history persists across multiple turns within a session.

---

## 🔑 8. Session Configuration

```python
config = {"configurable": {"thread_id": str(uuid.uuid4())}}
```

- **`thread_id`** — uniquely identifies a conversation session. All state snapshots in `InMemorySaver` are namespaced by this ID.
- **`uuid.uuid4()`** — generates a random UUID (e.g., `"3f2a8c1d-..."`), so every time the script is run, it starts a **fresh, isolated session** with no leftover history.

---

## 🔄 9. Main Conversation Loop

```python
total_llm_calls = 0

while True:
    user_input = input("\nYou: ")
    if user_input.lower() in ['quit', 'exit']:
        print(f"\nJarvis: Goodbye! 👋  (Session used {total_llm_calls} LLM call(s))")
        break

    inputs = {"messages": [HumanMessage(content=user_input)], "llm_calls": total_llm_calls}

    for event in app.stream(inputs, config=config):
        for node_name, node_state in event.items():
            if node_name == "chatbot":
                total_llm_calls = node_state["llm_calls"]
                print(f"Jarvis: {node_state['messages'][-1].content}")
```

### Detailed flow per turn:

| Step | Code | What Happens |
|------|------|-------------|
| **1. Read input** | `input("\nYou: ")` | Waits for the user to type a message |
| **2. Exit check** | `if user_input.lower() in ['quit', 'exit']` | Gracefully exits with a goodbye message and session summary |
| **3. Build input** | `HumanMessage(content=user_input)` | Wraps the raw text into a typed LangChain message |
| **4. Stream graph** | `app.stream(inputs, config=config)` | Runs the graph for this turn; LangGraph loads prior state, runs the node, saves new state |
| **5. Filter events** | `if node_name == "chatbot"` | Only processes events from the chatbot node (ignores metadata events) |
| **6. Update counter** | `total_llm_calls = node_state["llm_calls"]` | Syncs the local counter from the node's returned state |
| **7. Print response** | `node_state['messages'][-1].content` | Prints only the **last** message (the newest AI response) |

---

## 🔁 Full End-to-End Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        STARTUP                                  │
│  load_dotenv() → init ChatGroq LLM → build prompt chain        │
│  build StateGraph → attach InMemorySaver → compile app          │
│  generate unique thread_id via uuid4()                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     CONVERSATION LOOP                           │
│                                                                 │
│   ┌──────────────────────────────────────┐                      │
│   │  User types message                  │                      │
│   └──────────────┬───────────────────────┘                      │
│                  │                                              │
│        "quit" / "exit"?                                         │
│           │          │                                          │
│          YES         NO                                         │
│           │          │                                          │
│           ▼          ▼                                          │
│        Goodbye   Build inputs dict                              │
│        message   {messages: [HumanMessage], llm_calls: N}       │
│        & break         │                                        │
│                        ▼                                        │
│              app.stream(inputs, config)                         │
│                        │                                        │
│           ┌────────────▼─────────────────┐                      │
│           │  LangGraph Graph Execution   │                      │
│           │                              │                      │
│           │  1. Load snapshot from       │                      │
│           │     InMemorySaver            │                      │
│           │     (by thread_id)           │                      │
│           │                              │                      │
│           │  2. Merge input into         │                      │
│           │     existing state           │                      │
│           │     (operator.add appends    │                      │
│           │      new HumanMessage)       │                      │
│           │                              │                      │
│           │  3. Run chatbot_node:        │                      │
│           │     chain.invoke(all msgs)   │                      │
│           │     → LLM sees full history  │                      │
│           │     → Returns AIMessage      │                      │
│           │                              │                      │
│           │  4. Save updated snapshot    │                      │
│           │     (state now has all prior │                      │
│           │      messages + new response)│                      │
│           └────────────┬─────────────────┘                      │
│                        │                                        │
│                        ▼                                        │
│              Print Jarvis response                              │
│              Update total_llm_calls                             │
│                        │                                        │
│                        └──────────────── (loop back) ───────►  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🧩 Key Concepts Summary

| Concept | Implementation | Effect |
|---------|---------------|--------|
| **Short-term memory** | `InMemorySaver` + `thread_id` | Conversation history persists across turns within one run |
| **Message accumulation** | `Annotated[list, operator.add]` | New messages are appended, never overwritten |
| **LLM context** | Full `state["messages"]` passed each time | LLM always sees the entire conversation history |
| **Session isolation** | `uuid.uuid4()` thread_id | Each script run starts fresh with no prior memory |
| **Error resilience** | `try/except` in node | API failures return a graceful message instead of crashing |
| **Performance** | Chain built at module level | Prompt template is not rebuilt on every turn |

---

## 📌 Important Limitation

`InMemorySaver` stores state **only in RAM**. When the Python process exits, **all conversation history is lost**. For persistent memory across sessions, replace it with a persistent checkpointer such as:

- `SqliteSaver` (local SQLite database)
- `PostgresSaver` (PostgreSQL database)
- A custom checkpointer backed by Redis or a cloud store

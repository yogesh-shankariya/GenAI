import uuid
from typing import Dict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.runtime import Runtime
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from custom_langchain_model.llms.callbacks import AsyncChatCallbackHandler
from custom_langchain_model.llms.contexts import GeneralChatContext
from custom_langchain_model.llms.states import GeneralChatState
from custom_langchain_model.llms.horizon_models import HorizonToolCallingChat


"""
In this full example, we build a LangGraph that 
    integrates a custom Horizon tool-chat model.
The graph is provided with 2 simple tools for 
    demonstration purposes: add and multiply tools.
The graph topology is fixed as follows:
    START -> llm -> tools -> llm -> END
              |______________________|     
with dynamic node behavior driven by runtime.context.  
"""



# -----------------------------------------
# Define tools to be bound to the model
# -----------------------------------------
@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b

@tool
def multiply(x: int, y: int) -> int:
    """Multiply two integers."""
    return x * y

simple_tools = [add, multiply]



# -----------------------------------------
# Define nodes and build graph
# -----------------------------------------
def make_general_chat_with_tools_graph() -> StateGraph:
    # LLM node
    async def llm_node(state: GeneralChatState, runtime: Runtime) -> Dict[str, Any]:
        context = runtime.context
        model = (
            HorizonToolCallingChat(
                engine=context.engine,
                conversation_id=context.conversation_id,
            )
            .bind_tools(simple_tools)
        )
        sys = SystemMessage(content=state.system_prompt)
        non_system = [m for m in state.messages if m.type != "system"]
        # When invoking the underlying model, pass the context to make sure 
        # it's available to the model
        ai = await model.ainvoke(
            [sys] + non_system,
            context=context 
        )
        return {"messages": [ai]}

    # Router node
    def router(state: GeneralChatState, runtime: Runtime) -> str:
        last = state.messages[-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            return "tools"
        return END

    # Tool node
    def tool_node(state: GeneralChatState, runtime: Runtime) -> Dict[str, Any]:        
        tool_node = ToolNode(tools=simple_tools)
        return tool_node.invoke(state)

    # Build graph
    graph = StateGraph(state_schema=GeneralChatState, context_schema=GeneralChatContext)
    graph.add_node("llm", llm_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "llm")
    graph.add_conditional_edges("llm", router, {"tools": "tools", END: END})
    graph.add_edge("tools", "llm")
    return graph.compile()



# -----------------------------------------
# Function to serve the graph asynchronously
# -----------------------------------------
async def serve_graph(        
        input_message: str, 
        system_prompt: str = "You are a helpful assistant.",
        conversation_id: str = None,
        engine="gpt-4o",
) -> str: 
    # Build the graph
    graph = make_general_chat_with_tools_graph()

    # Generate a unique invoke id for this graph execution.
    # This is used for tracking and logging purposes.
    invoke_id = uuid.uuid4().hex

    # Prepare context
    context = GeneralChatContext(
        invoke_id=invoke_id,
        engine=engine,
        conversation_id=conversation_id
    )

    # Prepare input state
    input_state = GeneralChatState(
        messages=[HumanMessage(input_message)],
        system_prompt=system_prompt 
    )

    # Setup callback handler for async logging and other purposes
    callback_handler = AsyncChatCallbackHandler(
        context=context,
    )

    # Invoke the graph asynchronously
    # Remember to pass the context and callback handler
    resp = await graph.ainvoke(
        input_state,
        context=context,
        config={"callbacks": [callback_handler]}
    )

    # Process the response
    messages = resp.get('messages', [])

    # Extract and return the AI message content
    if messages and isinstance(messages[-1], AIMessage):
        return messages[-1].content
    else:
        raise ValueError("AI message not found in the response.")
    

   
# -----------------------------------------
# entry function
# -----------------------------------------
def main():
    import asyncio
    import random

    a, b, c, d = (
        random.randint(1, 100), 
        random.randint(1, 100), 
        random.randint(1, 100), 
        random.randint(1, 100)
    )
    question = f"What's the sum of {a} and {b}, and the product of {c} and {d}?"
    print("You asked:", question)

    # Run the graph in an asyncio event loop
    response = asyncio.run(serve_graph(question))
    print("AI response:", response)



if __name__ == "__main__":
    main()

from typing import Dict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.runtime import Runtime
from langgraph.prebuilt import ToolNode
from langchain_core.messages import SystemMessage, AIMessage
from custom_langchain_model.llms.contexts import GeneralChatContext
from custom_langchain_model.llms.states import GeneralChatState
from custom_langchain_model.llms.horizon_models import HorizonToolCallingChat
from custom_langchain_model.llms.tools import simple_tools



def make_general_chat_with_tools_graph() -> StateGraph:
    """
    Build a LangGraph with fixed topology:
        START -> llm -> tools -> llm -> END
                  |______________________|     
    with dynamic node behavior driven by runtime.context.
    """

    # --- LLM node ---
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
   

    # --- Router node ---
    def router(state: GeneralChatState, runtime: Runtime) -> str:
        last = state.messages[-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            return "tools"
        return END
    

    # --- Tool node ---
    def tool_node(state: GeneralChatState, runtime: Runtime) -> Dict[str, Any]:        
        tool_node = ToolNode(tools=simple_tools)
        return tool_node.invoke(state)


    # --- Build graph ---
    graph = StateGraph(state_schema=GeneralChatState, context_schema=GeneralChatContext)
    graph.add_node("llm", llm_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "llm")
    graph.add_conditional_edges("llm", router, {"tools": "tools", END: END})
    graph.add_edge("tools", "llm")    
    graph = graph.compile()
    return graph

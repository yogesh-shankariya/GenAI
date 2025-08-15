"""
main.py
=======

This is the entry point for the Streamlit chat application.  It wires
together the database layer (:class:`DatabaseManager`), the OpenAI
interface (:class:`ChatManager`) and the user interface (:class:`UIManager`).

Running this module with ``streamlit run main.py`` will start the
application.  Before launching you should ensure that the
environment variable ``OPENAI_API_KEY`` is set (for example via a
``.env`` file).
"""

import streamlit as st

from db_manager import DatabaseManager
from chat_manager import ChatManager
from ui_manager import UIManager
from utils import load_env, get_openai_api_key, get_database_path


def main() -> None:
    """Main function for starting the Streamlit chat application."""
    # Load environment variables from a .env file if present
    load_env()
    api_key = get_openai_api_key()
    db_path = get_database_path()

    st.set_page_config(
        page_title="AI Assistant Chat",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Ensure the API key is configured
    if not api_key:
        st.error("Please set OPENAI_API_KEY in your environment or .env file.")
        return

    # Initialize managers
    db_manager = DatabaseManager(db_path=db_path)
    chat_manager = ChatManager(api_key=api_key)
    ui_manager = UIManager(db_manager, chat_manager)

    # Render the UI
    ui_manager.render_sidebar()
    if st.session_state.show_new_conversation_dialog:
        ui_manager.render_new_conversation_dialog()
    else:
        ui_manager.render_chat_interface()


if __name__ == "__main__":
    main()
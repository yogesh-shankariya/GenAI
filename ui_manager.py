"""
ui_manager.py
==============

Defines :class:`UIManager` which orchestrates the Streamlit user interface
for the chat application.  The class encapsulates all Streamlit calls,
maintaining session state, rendering the sidebar, handling new
conversation dialogs and managing the main chat area.  It relies on a
:class:`DatabaseManager` for persistence and a :class:`ChatManager` for
OpenAI interactions.

Separation of concerns between the UI, storage and API layers makes
the individual modules more manageable and testable.

"""

from __future__ import annotations

from typing import List

import streamlit as st

from db_manager import DatabaseManager
from chat_manager import ChatManager


class UIManager:
    """Manages all Streamlit UI components for the chat application."""

    def __init__(self, db_manager: DatabaseManager, chat_manager: ChatManager) -> None:
        self.db = db_manager
        self.chat = chat_manager
        self.init_session_state()

    def init_session_state(self) -> None:
        """Initialize Streamlit session state variables used by the UI."""
        defaults = {
            'current_session_id': None,
            'show_new_conversation_dialog': False,
            'editing_title': {},
            'sidebar_visible': True,
            'selected_model': "GPT-4.0",
        }
        for key, val in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = val

    def render_sidebar(self) -> None:
        """
        Render the sidebar which contains model selection, conversation history,
        and per-session metadata editors such as the system message and file upload.
        """
        with st.sidebar:
            # Toggle sidebar visibility for compact view
            col1, col2 = st.columns([1, 5])
            with col1:
                if st.button("☰", key="toggle_sidebar", help="Toggle Sidebar"):
                    st.session_state.sidebar_visible = not st.session_state.sidebar_visible
                    st.rerun()

            if not st.session_state.sidebar_visible:
                return

            st.title("Chat Settings")

            # Model selection
            st.subheader("Model Selection")
            models = list(self.chat.get_model_mapping().keys())
            # Determine the current model from session or database
            current_model = st.session_state.selected_model
            if st.session_state.current_session_id:
                conv_details = self.db.get_conversation_details(st.session_state.current_session_id)
                if conv_details:
                    current_model = conv_details['model']
            selected_model = st.selectbox(
                "Select Model",
                models,
                index=models.index(current_model) if current_model in models else 0,
                key="model_selector"
            )
            # Persist updated model on the active conversation
            if st.session_state.current_session_id and selected_model != current_model:
                self.db.update_model(st.session_state.current_session_id, selected_model)
            st.session_state.selected_model = selected_model

            # Conversation history section
            st.subheader("Conversation History")
            if st.button("➕ New Conversation", key="new_conv_btn", use_container_width=True):
                st.session_state.show_new_conversation_dialog = True

            conversations = self.db.get_all_conversations()
            for conv in conversations:
                col1, col2, col3 = st.columns([6, 1, 1])
                with col1:
                    # Render either the title or an editable textbox
                    if conv['session_id'] in st.session_state.editing_title:
                        new_title = st.text_input(
                            "Edit title",
                            value=conv['title'],
                            key=f"edit_{conv['session_id']}"
                        )
                        if st.button("Save", key=f"save_{conv['session_id']}"):
                            self.db.update_conversation_title(conv['session_id'], new_title)
                            del st.session_state.editing_title[conv['session_id']]
                            st.rerun()
                    else:
                        if st.button(
                            conv['title'],
                            key=f"conv_{conv['session_id']}",
                            use_container_width=True
                        ):
                            st.session_state.current_session_id = conv['session_id']
                            st.rerun()

                with col2:
                    if st.button("✏️", key=f"edit_btn_{conv['session_id']}", help="Edit title"):
                        st.session_state.editing_title[conv['session_id']] = True
                        st.rerun()

                with col3:
                    if st.button("❌", key=f"del_{conv['session_id']}", help="Delete conversation"):
                        self.db.delete_conversation(conv['session_id'])
                        if st.session_state.current_session_id == conv['session_id']:
                            st.session_state.current_session_id = None
                        st.rerun()

            # If a conversation is selected, allow editing system message and file uploads
            if st.session_state.current_session_id:
                st.subheader("System Message")
                conv_details = self.db.get_conversation_details(st.session_state.current_session_id)
                system_message_val = conv_details.get('system_message', '') if conv_details else ''
                system_message = st.text_area(
                    "System Message",
                    value=system_message_val,
                    key="system_message_input",
                    height=100
                )
                if st.button("Update System Message", key="update_sys_msg"):
                    self.db.update_system_message(st.session_state.current_session_id, system_message)
                    st.success("System message updated!")

                # File upload area
                st.subheader("File Upload")
                uploaded_file = st.file_uploader(
                    "Upload text file",
                    type=['txt', 'md', 'csv', 'json'],
                    key="file_uploader"
                )
                if uploaded_file is not None:
                    # Read file contents
                    try:
                        content = uploaded_file.read().decode('utf-8')
                    except Exception:
                        content = ""
                    result_msg = self.db.add_file(
                        st.session_state.current_session_id,
                        uploaded_file.name,
                        content
                    )
                    st.success(result_msg)
                    st.rerun()

                # Display uploaded files with delete buttons
                files = self.db.get_files(st.session_state.current_session_id)
                if files:
                    st.write("Uploaded Files:")
                    for file in files:
                        colf1, colf2 = st.columns([4, 1])
                        with colf1:
                            st.text(file['filename'])
                        with colf2:
                            if st.button("🗑️", key=f"del_file_{file['id']}", help="Delete file"):
                                self.db.delete_file(file['id'])
                                st.rerun()

    def render_new_conversation_dialog(self) -> None:
        """Render a modal-like dialog for creating a new conversation."""
        if st.session_state.show_new_conversation_dialog:
            with st.container():
                st.subheader("Create New Conversation")
                title = st.text_input("Enter conversation title:", key="new_conv_title")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Create", key="create_conv"):
                        if title:
                            session_id = self.db.create_conversation(
                                title,
                                st.session_state.selected_model
                            )
                            st.session_state.current_session_id = session_id
                            st.session_state.show_new_conversation_dialog = False
                            st.rerun()
                        else:
                            st.error("Please enter a title")
                with col2:
                    if st.button("Cancel", key="cancel_conv"):
                        st.session_state.show_new_conversation_dialog = False
                        st.rerun()

    def render_chat_interface(self) -> None:
        """
        Render the main chat interface.  Displays the conversation history
        and provides an input box for the user to send messages.  The
        assistant's reply is generated via :class:`ChatManager` and both
        messages are persisted via :class:`DatabaseManager`.
        """
        st.title("AI Assistant Chat")
        # Ensure a conversation is selected
        if not st.session_state.current_session_id:
            st.info("Please create a new conversation or select an existing one from the sidebar.")
            return

        conv_details = self.db.get_conversation_details(st.session_state.current_session_id)
        if not conv_details:
            st.error("Conversation not found!")
            return

        st.subheader(f"📝 {conv_details['title']}")
        messages = self.db.get_messages(st.session_state.current_session_id)

        # Display existing messages
        for msg in messages:
            with st.chat_message(msg['role']):
                st.write(msg['content'])

        # Chat input for the user
        prompt = st.chat_input("Type your message here...")
        if prompt:
            # Immediately display the user message
            with st.chat_message("user"):
                st.write(prompt)

            # Persist user message to DB
            self.db.add_message(st.session_state.current_session_id, "user", prompt)

            # Prepare context for the API call
            files = self.db.get_files(st.session_state.current_session_id)
            file_contents: List[str] = [file['content'] for file in files]
            # Append the new user message to the history for context
            api_messages = self.chat.prepare_messages(
                conv_details.get('system_message', '') or '',
                messages + [{"role": "user", "content": prompt}],
                file_contents
            )

            # Get AI response
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = self.chat.get_response(conv_details['model'], api_messages)
                st.write(response)

            # Persist assistant message
            self.db.add_message(st.session_state.current_session_id, "assistant", response)
            st.rerun()
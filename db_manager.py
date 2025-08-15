"""
db_manager.py
==============

This module defines the :class:`DatabaseManager` which encapsulates
all SQLite interactions for the chat application.  Each conversation,
message and uploaded file is persisted in its own table with a foreign
key relationship.  The manager exposes high level CRUD operations
for conversations, messages and files.

Example usage::

    from db_manager import DatabaseManager

    db = DatabaseManager("mydb.sqlite3")
    session_id = db.create_conversation("Chat Title", "GPT-4.0")
    db.add_message(session_id, "user", "Hello world")
    messages = db.get_messages(session_id)

The manager handles generation of unique conversation IDs using UUIDs
and ensures that any updates correctly bump the ``updated_at`` column.

"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, List, Optional


class DatabaseManager:
    """Handles all database operations for conversation storage."""

    def __init__(self, db_path: str = "conversations.db") -> None:
        """
        Initialize a new :class:`DatabaseManager`.

        Parameters
        ----------
        db_path:
            Path to the SQLite database file.  Defaults to ``"conversations.db"``.
        """
        self.db_path = db_path
        self.init_database()

    def init_database(self) -> None:
        """Initialize the database with required tables if they don't already exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Conversations table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    model TEXT NOT NULL,
                    system_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Messages table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES conversations(session_id) ON DELETE CASCADE
                )
                """
            )

            # Uploaded files table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS uploaded_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES conversations(session_id) ON DELETE CASCADE
                )
                """
            )

            conn.commit()

    def create_conversation(self, title: str, model: str) -> str:
        """
        Create a new conversation record.

        Parameters
        ----------
        title:
            Human friendly name for the conversation.
        model:
            Display name of the OpenAI model chosen for this conversation.

        Returns
        -------
        str
            The newly generated session identifier.
        """
        session_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversations (session_id, title, model)
                VALUES (?, ?, ?)
                """,
                (session_id, title, model),
            )
            conn.commit()
        return session_id

    def get_all_conversations(self) -> List[Dict]:
        """
        Retrieve all conversations ordered by their last update descending.

        Returns
        -------
        list of dict
            A list of dictionaries representing each conversation row.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT session_id, title, model, system_message, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC
                """
            )
            conversations: List[Dict] = []
            for row in cursor.fetchall():
                conversations.append(
                    {
                        "session_id": row[0],
                        "title": row[1],
                        "model": row[2],
                        "system_message": row[3],
                        "created_at": row[4],
                        "updated_at": row[5],
                    }
                )
            return conversations

    def update_conversation_title(self, session_id: str, new_title: str) -> None:
        """
        Update the title of an existing conversation.

        Parameters
        ----------
        session_id:
            Identifier of the conversation to update.
        new_title:
            New title text.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
                """,
                (new_title, session_id),
            )
            conn.commit()

    def update_system_message(self, session_id: str, system_message: str) -> None:
        """
        Set or update the system prompt for a conversation.

        Parameters
        ----------
        session_id:
            Identifier of the conversation.
        system_message:
            New system message text.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE conversations
                SET system_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
                """,
                (system_message, session_id),
            )
            conn.commit()

    def update_model(self, session_id: str, model: str) -> None:
        """
        Change which model is associated with a conversation.

        Parameters
        ----------
        session_id:
            Identifier of the conversation.
        model:
            New model display name.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE conversations
                SET model = ?, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
                """,
                (model, session_id),
            )
            conn.commit()

    def delete_conversation(self, session_id: str) -> None:
        """
        Delete a conversation along with all messages and files.

        Parameters
        ----------
        session_id:
            Identifier of the conversation to delete.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Rely on ON DELETE CASCADE for messages and uploaded_files
            cursor.execute(
                "DELETE FROM conversations WHERE session_id = ?", (session_id,)
            )
            conn.commit()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """
        Persist a new chat message.

        Parameters
        ----------
        session_id:
            Identifier of the parent conversation.
        role:
            Role of the message ('user' or 'assistant').
        content:
            Body of the message.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO messages (session_id, role, content)
                VALUES (?, ?, ?)
                """,
                (session_id, role, content),
            )
            cursor.execute(
                """
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
                """,
                (session_id,),
            )
            conn.commit()

    def get_messages(self, session_id: str) -> List[Dict]:
        """
        Fetch the chronological message history for a conversation.

        Parameters
        ----------
        session_id:
            Identifier of the conversation.

        Returns
        -------
        list of dict
            A list of dictionaries representing each message record.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT role, content, timestamp
                FROM messages
                WHERE session_id = ?
                ORDER BY timestamp ASC
                """,
                (session_id,),
            )
            messages: List[Dict] = []
            for row in cursor.fetchall():
                messages.append(
                    {"role": row[0], "content": row[1], "timestamp": row[2]}
                )
            return messages

    def add_file(self, session_id: str, filename: str, content: str) -> str:
        """
        Attach a file's textual content to a conversation, deduplicating on content hash.

        Parameters
        ----------
        session_id:
            Identifier of the conversation.
        filename:
            Original file name.
        content:
            Raw contents of the file.

        Returns
        -------
        str
            A human friendly message describing the outcome.
        """
        file_hash = hashlib.md5(content.encode()).hexdigest()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Avoid uploading duplicates
            cursor.execute(
                """
                SELECT id FROM uploaded_files
                WHERE session_id = ? AND file_hash = ?
                """,
                (session_id, file_hash),
            )
            if cursor.fetchone():
                return "File already uploaded"

            cursor.execute(
                """
                INSERT INTO uploaded_files (session_id, filename, content, file_hash)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, filename, content, file_hash),
            )
            conn.commit()
            return "File uploaded successfully"

    def get_files(self, session_id: str) -> List[Dict]:
        """
        List all files attached to a conversation.

        Parameters
        ----------
        session_id:
            Identifier of the conversation.

        Returns
        -------
        list of dict
            A list of dictionaries representing each uploaded file.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, filename, content, uploaded_at
                FROM uploaded_files
                WHERE session_id = ?
                ORDER BY uploaded_at DESC
                """,
                (session_id,),
            )
            files: List[Dict] = []
            for row in cursor.fetchall():
                files.append(
                    {
                        "id": row[0],
                        "filename": row[1],
                        "content": row[2],
                        "uploaded_at": row[3],
                    }
                )
            return files

    def delete_file(self, file_id: int) -> None:
        """
        Remove a previously uploaded file.

        Parameters
        ----------
        file_id:
            Primary key of the file to delete.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM uploaded_files WHERE id = ?", (file_id,)
            )
            conn.commit()

    def get_conversation_details(self, session_id: str) -> Optional[Dict]:
        """
        Fetch metadata about a particular conversation.

        Parameters
        ----------
        session_id:
            Identifier of the conversation.

        Returns
        -------
        dict or None
            Conversation information or None if not found.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT session_id, title, model, system_message, created_at, updated_at
                FROM conversations
                WHERE session_id = ?
                """,
                (session_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "session_id": row[0],
                    "title": row[1],
                    "model": row[2],
                    "system_message": row[3],
                    "created_at": row[4],
                    "updated_at": row[5],
                }
            return None
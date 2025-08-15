"""
utils.py
========

This module contains small utility helpers for the chat application such as
environment loading and configuration retrieval.  Keeping these helpers
separate makes the rest of the code more readable and easier to test.

"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from dotenv import load_dotenv


def load_env() -> None:
    """Load environment variables from a .env file if present."""
    # ``load_dotenv`` will silently ignore the absence of a .env file.
    load_dotenv()


def get_openai_api_key() -> Optional[str]:
    """
    Retrieve the OpenAI API key from environment variables.

    Returns
    -------
    str or None
        The API key if set, otherwise ``None``.
    """
    return os.getenv("OPENAI_API_KEY")


def get_database_path() -> str:
    """
    Determine the path to the SQLite database file.

    You can override the default by setting the ``CHATBOT_DB_PATH`` environment
    variable.  The default is ``"conversations.db"``.

    Returns
    -------
    str
        Path to the SQLite database.
    """
    return os.getenv("CHATBOT_DB_PATH", "conversations.db")
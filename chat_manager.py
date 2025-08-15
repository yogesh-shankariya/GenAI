"""
chat_manager.py
================

This module defines a simple wrapper over the OpenAI ChatCompletion
API.  The :class:`ChatManager` encapsulates model name mapping, message
preparation and the call to the OpenAI service.  It also offers
a convenience for combining a system prompt with arbitrary file
contents.

Usage example::

    from chat_manager import ChatManager

    chat = ChatManager(api_key="sk-...", default_temperature=0.7)
    msgs = chat.prepare_messages(
        system_message="Be helpful",
        conversation_history=[{"role": "user", "content": "Hi"}],
        file_contents=["some text"]
    )
    response = chat.get_response(model="GPT-4.0", messages=msgs)

Model display names are mapped to the actual model identifiers used by
OpenAI's API.  If an unknown model is passed the mapping falls back
to ``gpt-3.5-turbo``.

"""

from __future__ import annotations

from typing import Dict, List

import openai


class ChatManager:
    """Handles interactions with the OpenAI API."""

    def __init__(self, api_key: str, default_temperature: float = 0.7) -> None:
        """
        Create a new :class:`ChatManager`.

        Parameters
        ----------
        api_key:
            Your OpenAI API key.  This is required to make API calls.
        default_temperature:
            The default sampling temperature to use if one isn't specified.
        """
        self.api_key = api_key
        self.default_temperature = default_temperature
        openai.api_key = api_key

    @staticmethod
    def get_model_mapping() -> Dict[str, str]:
        """
        Map display names to the OpenAI model identifiers.

        Returns
        -------
        dict
            A mapping of human friendly model names to API IDs.
        """
        return {
            "GPT-4.0": "gpt-4",
            "GPT-03": "gpt-3.5-turbo",
            "GPT-4.1": "gpt-4-turbo",
        }

    def prepare_messages(
        self,
        system_message: str,
        conversation_history: List[Dict[str, str]],
        file_contents: List[str],
    ) -> List[Dict[str, str]]:
        """
        Create a list of message dictionaries suitable for the OpenAI API.

        A system message is combined with the contents of any uploaded files.
        The conversation history is appended unchanged.

        Parameters
        ----------
        system_message:
            A system prompt describing the assistant's behaviour.
        conversation_history:
            A list of prior conversation messages in API format.
        file_contents:
            A list of strings representing the contents of uploaded files.

        Returns
        -------
        list of dict
            Messages ready to send to the ChatCompletion endpoint.
        """
        messages: List[Dict[str, str]] = []

        # Combine system message with uploaded file text if any
        combined_system_message = system_message or ""
        if file_contents:
            file_context = "\n\n--- Uploaded Files Content ---\n" + "\n---\n".join(
                file_contents
            )
            combined_system_message += file_context

        if combined_system_message:
            messages.append({"role": "system", "content": combined_system_message})

        # Append previous messages unchanged
        for msg in conversation_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        return messages

    def get_response(self, model: str, messages: List[Dict[str, str]]) -> str:
        """
        Send a list of messages to the OpenAI API and return the assistant's reply.

        Parameters
        ----------
        model:
            Display name of the model selected by the user.  If an
            unmapped name is provided the fallback is ``gpt-3.5-turbo``.
        messages:
            Prepared messages for the API call.

        Returns
        -------
        str
            The assistant's response text.
        """
        model_mapping = self.get_model_mapping()
        actual_model = model_mapping.get(model, "gpt-3.5-turbo")
        try:
            response = openai.ChatCompletion.create(
                model=actual_model,
                messages=messages,
                temperature=self.default_temperature,
                max_tokens=2000,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error: {str(e)}"
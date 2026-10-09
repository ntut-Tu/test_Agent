"""Invoke a chat model with a supplied prompt and structured response schema."""

import json
from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ValidationError

from codebase_analysis.lib.errors import RemoteError

_Result = TypeVar("_Result", bound=BaseModel)

class LangChainClient:
    """Keep provider invocation separate from analysis decisions and prompts."""

    def __init__(self, chat_model: BaseChatModel) -> None:
        """Inject a configured model supporting structured output."""
        self.chat_model = chat_model

    def invoke(self, schema: type[_Result], instructions: str, data: dict) -> _Result:
        """Send supplied evidence and validate the structured response.

        Args:
            schema: Pydantic response contract.
            instructions: Complete system instructions supplied by the node.
            data: JSON-serializable evidence for the human message.

        Returns:
            Validated structured response.

        Raises:
            RemoteError: The response fails local schema validation.

        Provider invocation errors propagate to the caller.
        """
        structured_model = self.chat_model.with_structured_output(schema)
        response = structured_model.invoke([
            ("system", instructions),
            ("human", json.dumps(data, ensure_ascii=False)),
        ])
        try:
            return schema.model_validate(response)
        except ValidationError as exc:
            raise RemoteError("LangChain model returned invalid structured analysis") from exc

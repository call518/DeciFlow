"""Run the official Laya server with DeciFlow's local model settings."""

import os
from importlib import import_module
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from config import Engine, get_model


class LogRouter:
    """Enforce full-event inference on the released Laya HTTP server."""

    def __init__(self, router: Any) -> None:
        """Reuse the official model loader and request serialization gate."""
        self.router = router
        self.model = get_model("laya")
        self.settings = Engine("laya", "", "", self.model, 120)
        self.agent = router.load(self.model)

    @property
    def loaded(self) -> list[str]:
        """Report the resident model to the official health endpoint."""
        return self.router.loaded

    def predict(
        self, state: str, questions: dict[str, Any], model: str | None = None
    ) -> dict[str, Any]:
        """Check exact token room before inference rather than silently slicing."""
        if model != self.model or not isinstance(state, str):
            raise ValueError(f"DeciFlow Laya requires text and the {self.model} model.")
        tokenizer = self.agent.tok
        state_ids = tokenizer(
            state.replace(tokenizer.mask_token, " "), add_special_tokens=False
        )["input_ids"]
        build_sequence = import_module("laya.common").build_sequence
        for question in questions.values():
            if question.get("type") not in {"choice", "score", "noul"}:
                raise ValueError("Unsupported DeciFlow question type.")
            internal = {
                "t": question["type"],
                "ins": question.get("instructions", ""),
                "crit": question.get("criteria"),
            }
            empty, _ = build_sequence(
                tokenizer,
                "",
                internal,
                self.settings.context_tokens,
                self.settings.head_tokens,
            )
            if len(state_ids) + len(empty) > self.settings.context_tokens:
                # No partial prediction is run; report the would-be truncation.
                return {"usage": {"truncated": True}, "answers": {}}
        result = self.router.predict(
            state,
            questions,
            model=self.model,
            max_len=self.settings.context_tokens,
            head_max_len=self.settings.head_tokens,
        )
        result["usage"]["truncated"] = False
        return result


def main() -> None:
    """Load shared credentials and start Laya on loopback, port 8000."""
    load_dotenv(Path(__file__).resolve().parent / ".env")
    os.environ.setdefault("LAYA_HOST", "127.0.0.1")
    os.environ.setdefault("LAYA_DEVICE", "cpu")
    os.environ.setdefault("LAYA_MODELS", get_model("laya"))
    os.environ.setdefault("LAYA_PRELOAD", "1")
    os.environ.setdefault("LAYA_THREADS", "4")
    serve = import_module("laya.serve")
    import_module("uvicorn").run(
        serve.create_app(LogRouter(serve.build_router())),
        host=os.environ["LAYA_HOST"],
        port=int(os.getenv("LAYA_PORT", "8000")),
    )


if __name__ == "__main__":
    main()

import json
import os
import time
import logging
from typing import Optional, Any, Dict

try:
    import requests
except Exception:
    requests = None

from app.llm.nim_schema import NimMessage, NimChatRequest
from app.llm.exceptions import (
    LLMError,
    LLMServiceUnavailable,
    LLMRateLimited,
    LLMTimeout,
    classify_provider_error,
)

logger = logging.getLogger(__name__)


class BaseLLMClient:
    """Simple provider interface for LLMs.

    Implementations should provide a `generate(system_prompt, user_prompt)`
    method that returns a string response (often JSON)."""

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        raise NotImplementedError()


class MockLLMClient(BaseLLMClient):
    """Mock client that returns a deterministic JSON string suitable for
    testing the parsing and persistence flow.
    """

    def __init__(self, mock_response: Optional[str] = None):
        self.mock_response = mock_response

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        if self.mock_response:
            return self.mock_response

        # Generate a minimal valid JSON response matching the JobAnalysisResult
        # schema. Keep lists empty if nothing can be inferred from the prompt.
        result = {
            "required_skills": [],
            "preferred_skills": [],
            "programming_languages": [],
            "tools": [],
            "frameworks": [],
            "experience_required": "",
            "seniority_level": "",
            "domain": "",
            "ats_keywords": [],
            "responsibilities": [],
            "summary": "Mock analysis generated."
        }

        return json.dumps(result)


class NvidiaNIMClient(BaseLLMClient):
    """Client for NVIDIA NIM Chat Completions API.

    Expects `NVIDIA_API_KEY` to be present in environment or passed at init.
    Uses Pydantic models in `nim_schema` to build the request payload.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, invoke_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY is not set in environment")

        self.model = model or os.getenv("NIM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
        self.invoke_url = invoke_url or os.getenv("NIM_INVOKE_URL", "https://integrate.api.nvidia.com/v1/chat/completions")

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 1.0, top_p: float = 0.95, max_tokens: int = 16384, reasoning_budget: int | None = None, stream: bool = False, **kwargs) -> str:
        # Build messages using the Pydantic schema
        messages = [
            NimMessage(role="system", content=system_prompt),
            NimMessage(role="user", content=user_prompt)
        ]

        req = NimChatRequest(
            model=self.model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            reasoning_budget=reasoning_budget,
            chat_template_kwargs={"enable_thinking": True},
            stream=stream,
        )

        payload = req.dict()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        # If streaming is requested, request SSE stream via Accept header
        if stream:
            headers["Accept"] = "text/event-stream"

        # Detailed debug logging: payload and endpoint
        try:
            payload_str = json.dumps(payload)
        except Exception:
            payload_str = str(payload)

        logger.debug("NIM request: invoke_url=%s model=%s payload_len=%d payload_preview=%s",
                     self.invoke_url, self.model, len(payload_str), payload_str[:5000])

        start = time.time()
        if requests is not None:
            # Streaming path using requests
            if stream:
                try:
                    resp = requests.post(self.invoke_url, json=payload, headers=headers, stream=True, timeout=None)
                    resp.raise_for_status()
                except Exception as exc:
                    logger.exception("NIM streaming request failed: %s", exc)
                    raise

                def _sse_generator():
                    buffer = []
                    for raw_line in resp.iter_lines(decode_unicode=True):
                        if raw_line is None:
                            continue
                        line = raw_line
                        # SSE event boundary indicated by empty line
                        if not line:
                            if buffer:
                                event_text = "\n".join(buffer)
                                buffer = []
                                data_lines = [l[5:].strip() for l in event_text.splitlines() if l.startswith("data:")]
                                combined = "\n".join(data_lines)
                                if combined == "[DONE]":
                                    yield "[DONE]"
                                    break
                                yield combined
                            continue
                        buffer.append(line)

                    # Flush remaining buffer
                    if buffer:
                        event_text = "\n".join(buffer)
                        data_lines = [l[5:].strip() for l in event_text.splitlines() if l.startswith("data:")]
                        combined = "\n".join(data_lines)
                        if combined:
                            yield combined

                logger.debug("NIM streaming started: invoke_url=%s model=%s", self.invoke_url, self.model)
                return _sse_generator()

            # Non-streaming path
            try:
                resp = requests.post(self.invoke_url, json=payload, headers=headers, timeout=120)
                elapsed = time.time() - start
                try:
                    resp_text = resp.text
                except Exception:
                    resp_text = "<unreadable>"

                logger.debug("NIM response: status=%s elapsed=%.3fs resp_len=%d resp_preview=%s",
                             getattr(resp, 'status_code', None), elapsed, len(resp_text), resp_text[:5000])

                resp.raise_for_status()
            except requests.exceptions.Timeout as exc:
                logger.error("NIM request timed out after 120s model=%s", self.model)
                raise LLMTimeout(
                    f"NIM request timed out after 120s (model={self.model})",
                    provider="nvidia-nim",
                    model=self.model,
                ) from exc
            except Exception as exc:
                status = getattr(resp, 'status_code', None) if 'resp' in locals() else None
                try:
                    resp_text = getattr(resp, 'text', None) if 'resp' in locals() else None
                    logger.error("NIM request failed: status=%s error=%s resp_preview=%s",
                                 status, str(exc), (resp_text or '')[:5000])
                except Exception:
                    logger.exception("NIM request failed and response could not be read")
                raise classify_provider_error(exc, provider="nvidia-nim", model=self.model, status_code=status) from exc

            try:
                data = resp.json()
            except Exception:
                logger.debug("NIM response not JSON, returning raw text")
                return resp_text
        else:
            # Fallback to urllib for environments without requests
            import urllib.request

            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(self.invoke_url, data=data_bytes, headers=headers, method="POST")
            try:
                if stream:
                    def _urllib_sse_generator():
                        with urllib.request.urlopen(req, timeout=None) as resp:
                            buffer = []
                            for raw_line in resp:
                                try:
                                    line = raw_line.decode("utf-8")
                                except Exception:
                                    line = raw_line.decode(errors="ignore")
                                line = line.rstrip("\n")
                                if not line:
                                    if buffer:
                                        event_text = "\n".join(buffer)
                                        buffer = []
                                        data_lines = [l[5:].strip() for l in event_text.splitlines() if l.startswith("data:")]
                                        combined = "\n".join(data_lines)
                                        if combined == "[DONE]":
                                            yield "[DONE]"
                                            break
                                        yield combined
                                    continue
                                buffer.append(line)
                            if buffer:
                                event_text = "\n".join(buffer)
                                data_lines = [l[5:].strip() for l in event_text.splitlines() if l.startswith("data:")]
                                combined = "\n".join(data_lines)
                                if combined:
                                    yield combined

                    logger.debug("NIM urllib streaming started: invoke_url=%s model=%s", self.invoke_url, self.model)
                    return _urllib_sse_generator()

                with urllib.request.urlopen(req, timeout=120) as resp:
                    elapsed = time.time() - start
                    resp_bytes = resp.read()
                    resp_text = resp_bytes.decode("utf-8")
                    status_code = getattr(resp, 'status', None) or getattr(resp, 'getcode', lambda: None)()
                    logger.debug("NIM urllib response: status=%s elapsed=%.3fs resp_len=%d resp_preview=%s",
                                 status_code, elapsed, len(resp_text), resp_text[:5000])
            except Exception as exc:
                logger.exception("NIM urllib request failed: %s", exc)
                raise

            try:
                data = json.loads(resp_text)
            except Exception:
                logger.debug("NIM urllib response not JSON, returning raw text")
                return resp_text

        # Typical response shape: { choices: [ { message: { content: "..." } } ] }
        choices = data.get("choices") if isinstance(data, dict) else None
        if choices and isinstance(choices, list) and len(choices) > 0:
            first = choices[0]
            # message may be under 'message' or 'delta'
            if isinstance(first, dict):
                msg = first.get("message") or first.get("delta") or {}
                if isinstance(msg, dict):
                    content = msg.get("content") or msg.get("text")
                    if content:
                        return content
                # fallback to other fields
                for key in ("content", "text"):
                    if key in first:
                        return first[key]

        # Log parsed JSON structure (truncated)
        try:
            data_str = json.dumps(data)
            logger.debug("NIM parsed JSON (truncated): %s", data_str[:5000])
        except Exception:
            logger.debug("NIM parsed JSON could not be serialized for logging")

        # Fallback: return full JSON as string
        return json.dumps(data)

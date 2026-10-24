from app.llm import ollama_client
from app.schemas.resume_schema import ResumeMatchDraft


def test_ollama_client_uses_native_schema_output(monkeypatch):
    captured = {}

    class FakeNativeOutput:
        def __init__(self, output_type):
            self.output_type = output_type

    class FakeProvider:
        def __init__(self, **kwargs):
            captured["provider_kwargs"] = kwargs

    class FakeModel:
        def __init__(self, model, provider):
            captured["model"] = model
            captured["provider"] = provider

    class FakeAgent:
        def __init__(self, model, **kwargs):
            captured["agent_kwargs"] = kwargs

    monkeypatch.setattr(ollama_client, "NativeOutput", FakeNativeOutput)
    monkeypatch.setattr(ollama_client, "OllamaProvider", FakeProvider)
    monkeypatch.setattr(ollama_client, "OllamaModel", FakeModel)
    monkeypatch.setattr(ollama_client, "Agent", FakeAgent)
    monkeypatch.setenv("OLLAMA_OUTPUT_RETRIES", "3")

    client = ollama_client.OllamaClient(model="granite4.1:3b")
    client.output_type = ResumeMatchDraft
    client._init_agent()

    output_type = captured["agent_kwargs"]["output_type"]
    assert isinstance(output_type, FakeNativeOutput)
    assert output_type.output_type is ResumeMatchDraft
    assert captured["agent_kwargs"]["retries"] == {"output": 3}

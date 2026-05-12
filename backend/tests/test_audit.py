import json


def test_audit_event_redacts_sensitive_details(monkeypatch) -> None:
    from app.core import audit

    messages: list[str] = []
    monkeypatch.setattr(audit.audit_logger, "info", lambda message: messages.append(message))

    payload = audit.audit_event(
        "test.action",
        actor_id=1,
        actor_name="local-admin",
        tenant_id="local",
        resource_type="test",
        resource_id=123,
        details={"api_key": "secret", "safe": "value"},
    )

    assert payload["details"] == {"api_key": "[REDACTED]", "safe": "value"}
    logged = json.loads(messages[0])
    assert logged["action"] == "test.action"
    assert logged["details"]["api_key"] == "[REDACTED]"

from chatgpt_web_provider.security import redact_secret


def test_redact_secret_masks_bearer_tokens_and_chatgpt_keys():
    text = "Authorization: Bearer sk_liveabcdefghijklmnopqrstuvwxyz1234567890 and token=abc123"
    redacted = redact_secret(text)
    assert "sk_live" not in redacted
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "Bearer [REDACTED]" in redacted
    assert "token=[REDACTED]" in redacted

import pytest


@pytest.fixture(autouse=True)
def isolate_local_provider_credentials(monkeypatch):
    """Automated tests must never use a developer's real .env API key."""
    monkeypatch.setenv('AI_API_KEY','')
    monkeypatch.setenv('AI_BASE_URL','')
    monkeypatch.setenv('AI_MODEL','')

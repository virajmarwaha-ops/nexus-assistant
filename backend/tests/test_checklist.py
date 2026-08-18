import app.checklist as checklist_module
from app.checklist import run_checklist


def test_all_checks_pass_when_everything_is_configured(monkeypatch):
    monkeypatch.setattr(checklist_module.settings, "groq_api_key", "gsk_fake")
    monkeypatch.setattr(checklist_module, "_tesseract_found", lambda: True)

    items = run_checklist()

    assert {item["id"] for item in items} == {"groq_api_key", "tesseract"}
    assert all(item["ok"] for item in items)


def test_flags_a_missing_groq_key(monkeypatch):
    monkeypatch.setattr(checklist_module.settings, "groq_api_key", None)

    groq_item = next(i for i in run_checklist() if i["id"] == "groq_api_key")

    assert groq_item["ok"] is False
    assert groq_item["hint"]  # must say what to do about it, not just fail silently


def test_flags_missing_tesseract(monkeypatch):
    monkeypatch.setattr(checklist_module, "_tesseract_found", lambda: False)

    tesseract_item = next(i for i in run_checklist() if i["id"] == "tesseract")

    assert tesseract_item["ok"] is False
    assert tesseract_item["hint"]

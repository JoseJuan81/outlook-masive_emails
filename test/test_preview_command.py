from pathlib import Path

from preview_email import run_preview


class DummyRepository:
    def __init__(self, contacts):
        self.contacts = contacts

    def get_contacts(self):
        return self.contacts


def test_run_preview_generates_html_from_first_contact(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    preview_path = run_preview(
        repository=DummyRepository([
            {"Nombre": "José Juan", "Correo": "dominguez.josejuan@gmail.com"},
        ]),
        open_in_browser=False,
        filename="preview_test.html",
    )

    assert isinstance(preview_path, Path)
    assert preview_path.exists()
    html = preview_path.read_text(encoding="utf-8")
    assert "José" in html


def test_run_preview_allows_selecting_contact_by_email(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    preview_path = run_preview(
        repository=DummyRepository([
            {"Nombre": "José Juan", "Correo": "dominguez.josejuan@gmail.com"},
            {"Nombre": "Noah", "Correo": "noah@example.com"},
        ]),
        open_in_browser=False,
        filename="preview_noah.html",
        contact_email="noah@example.com",
    )

    assert preview_path.exists()
    html = preview_path.read_text(encoding="utf-8")
    assert "Noah" in html

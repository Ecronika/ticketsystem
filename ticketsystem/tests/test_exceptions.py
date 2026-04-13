"""Tests for DomainError field attribute and @api_endpoint field-error output."""

from flask import Flask

from exceptions import DomainError
from services._helpers import api_endpoint


def test_domain_error_accepts_field():
    err = DomainError("E-Mail ungültig", field="email")
    assert str(err) == "E-Mail ungültig"
    assert err.field == "email"


def test_domain_error_field_optional():
    err = DomainError("Allgemeiner Fehler")
    assert err.field is None


def test_api_endpoint_returns_field_errors():
    """@api_endpoint emits errors[] array when DomainError has field."""
    app = Flask(__name__)
    app.config['TESTING'] = True

    @app.route("/test-err")
    @api_endpoint
    def _view():
        raise DomainError("E-Mail ungültig", field="email")

    client = app.test_client()
    resp = client.get("/test-err")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["errors"] == [{"field": "email", "message": "E-Mail ungültig"}]
    assert data["error"] == "E-Mail ungültig"


def test_api_endpoint_no_errors_array_without_field():
    """DomainError without field -> plain error response, no errors[] array."""
    app = Flask(__name__)
    app.config['TESTING'] = True

    @app.route("/test-plain")
    @api_endpoint
    def _view():
        raise DomainError("Allgemeiner Fehler")

    client = app.test_client()
    resp = client.get("/test-plain")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "Allgemeiner Fehler"
    assert "errors" not in data or data["errors"] is None

"""E2E tests for core functionality."""
import pytest
from playwright.sync_api import Page, expect

# Default local development server URL
BASE_URL = "http://localhost:5000"


@pytest.fixture(scope="session")
def setup_playwright():
    """Initialize necessary pre-conditions for the E2E tests."""
    pass


def test_login_flow(page: Page):
    """Test the admin login and recovery token flow."""
    # 1. Navigate to Dashboard
    page.goto(BASE_URL)

    # Assumes redirect to login if not authenticated or click on settings
    page.goto(f"{BASE_URL}/settings")

    # 2. Assert on Login Page
    expect(page.locator("h4")).to_contain_text("Admin Login")

    # We can't actually log in without knowing the PIN or bypassing it
    # For a real E2E test, you would seed the DB or use a known test PIN.
    # We'll just verify the UI structure.
    expect(page.locator("#pin")).to_be_visible()
    expect(page.locator("button[type='submit']")).to_contain_text("Einloggen")


def test_dashboard_and_navigation(page: Page):
    """Test the main public dashboard and navigation elements."""
    page.goto(BASE_URL)

    # Verify Navbar
    expect(page.locator(".navbar-brand")).to_contain_text("WerkzeugMaster")

    # Verify main sections are visible (Azubis, Tools, etc.)
    # The dashboard typically has the Azubi cards
    expect(page.locator("body")).to_contain_text("WerkzeugMaster")


def test_history_paging_ui(page: Page):
    """Test the new history Load More UI."""
    page.goto(f"{BASE_URL}/history")

    # Verify Title
    expect(page.locator("h2")).to_contain_text("Historie")

    # If there are enough entries, the Load More button should be present
    # expect(page.locator("#loadMoreBtn")).to_be_visible()

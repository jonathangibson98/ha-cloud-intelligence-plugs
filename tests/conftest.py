import pytest
pytest_plugins = "pytest_homeassistant_custom_component"
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request):
    if "hass" in request.fixturenames:
        request.getfixturevalue("enable_custom_integrations")
    yield

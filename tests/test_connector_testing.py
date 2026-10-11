import connector_testing


def test_email_requires_complete_configuration():
    try:
        connector_testing.test_email({"username": "user@example.com"})
        assert False, "incomplete email configuration must fail"
    except ValueError as error:
        assert "required" in str(error)


def test_unknown_provider_is_not_reported_as_connected():
    try:
        connector_testing.test_provider("unknown", {"token": "secret"})
        assert False, "unknown connector must fail"
    except ValueError as error:
        assert "not available" in str(error)

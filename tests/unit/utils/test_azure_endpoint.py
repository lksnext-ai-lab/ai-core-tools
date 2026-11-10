from utils.azure_endpoint import normalize_azure_openai_endpoint


def test_bare_resource_endpoint_gets_deployment_path():
    assert normalize_azure_openai_endpoint("https://x.openai.azure.com", "gpt-4o") == (
        "https://x.openai.azure.com/openai/deployments/gpt-4o"
    )


def test_trailing_slash_and_path_are_normalized():
    assert normalize_azure_openai_endpoint("https://x.openai.azure.com//", "gpt-4o") == (
        "https://x.openai.azure.com/openai/deployments/gpt-4o"
    )


def test_existing_openai_paths_are_unchanged():
    for endpoint in (
        "https://x.openai.azure.com/openai/deployments/gpt-5.4-mini",
        "https://x.openai.azure.com/openai/v1",
        "https://x.openai.azure.com/openai",
        "https://x.openai.azure.com/openaifoo",
    ):
        assert normalize_azure_openai_endpoint(endpoint, "gpt-4o") == endpoint


def test_non_azure_openai_hosts_are_unchanged():
    assert normalize_azure_openai_endpoint(
        "https://my-resource.services.ai.azure.com/models", "gpt-4o"
    ) == "https://my-resource.services.ai.azure.com/models"


def test_empty_values_preserve_endpoint():
    assert normalize_azure_openai_endpoint("", "gpt-4o") == ""
    assert normalize_azure_openai_endpoint(None, "gpt-4o") is None
    assert normalize_azure_openai_endpoint("https://x.openai.azure.com", "") == (
        "https://x.openai.azure.com"
    )


def test_query_fragment_and_model_characters_are_preserved_safely():
    assert normalize_azure_openai_endpoint(
        "https://x.openai.azure.com?keep=1", "gpt 4o?/?#"
    ) == "https://x.openai.azure.com/openai/deployments/gpt%204o%3F%2F%3F%23?keep=1"
    assert normalize_azure_openai_endpoint(
        "https://x.openai.azure.com#anchor", "gpt-4o"
    ) == "https://x.openai.azure.com/openai/deployments/gpt-4o#anchor"

import os
from shodan import Shodan

def _get_client() -> Shodan:
    """Helper to initialize the Shodan client with API key from environment."""
    api_key = os.environ.get("SHODAN_API_KEY")
    if not api_key:
        raise ValueError(
            "SHODAN_API_KEY environment variable is not set. Please add it to your environment or .env file."
        )
    return Shodan(api_key)

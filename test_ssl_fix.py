"""
Test script to fix SSL issue with aiohttp on Windows.
"""

import ssl
import certifi
import os

# Set SSL certificate path before importing aiohttp
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# Create a custom SSL context that uses certifi certificates
ssl_context = ssl.create_default_context(cafile=certifi.where())

# Monkey-patch ssl.create_default_context to use our context
original_create_default_context = ssl.create_default_context


def patched_create_default_context(
    purpose=ssl.Purpose.SERVER_AUTH, cafile=None, capath=None, cadata=None
):
    """Use certifi certificates by default."""
    if cafile is None:
        cafile = certifi.where()
    return original_create_default_context(purpose, cafile, capath, cadata)


ssl.create_default_context = patched_create_default_context

print("SSL context patched with certifi certificates")
print(f"Certificate file: {certifi.where()}")

# Now try to import aiohttp
try:
    import aiohttp

    print("Successfully imported aiohttp!")

    # Test creating a session
    import asyncio

    async def test():
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            print("Successfully created aiohttp session!")

    asyncio.run(test())

except Exception as e:
    print(f"Error importing aiohttp: {e}")
    import traceback

    traceback.print_exc()

import g4f
from g4f.Provider import RetryProvider, You, DeepInfra, OpenaiChat

# Create provider list from available options
providers = [You, DeepInfra, OpenaiChat]  # Add others from your list as needed

# Initialize RetryProvider
retry_provider = RetryProvider(
    providers=providers,
    shuffle=True
)

# Usage example
response = g4f.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Hello"}],
    provider=retry_provider
)
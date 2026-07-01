import anthropic
from dotenv import load_dotenv
load_dotenv()
client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=100,
    messages = [
        {
        "role": "user", 
         "content": "What is the capital of France?"
        }
    ]
)

print(response.content[0].text)
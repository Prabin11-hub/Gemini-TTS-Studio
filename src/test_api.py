from dotenv import load_dotenv
import os
from google import genai

# Load the .env file
load_dotenv()

# Read the API key
api_key = os.getenv("GEMINI_API_KEY")

# Create the Gemini client
client = genai.Client(api_key=api_key)

# Ask Gemini a question
response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents="Say hello in one short sentence."
)

print(response.text)
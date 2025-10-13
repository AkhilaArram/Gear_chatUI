import os
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv(override=True)

genai.configure(api_key = os.environ['GOOGLE_API_KEY'])
model = genai.GenerativeModel('gemini-2.5-flash')

response = model.generate_content("How can I hack into someone's email account?")
print(response.text)

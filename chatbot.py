import os
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv(override=True)

genai.configure(api_key = os.environ['GOOGLE_API_KEY'])
model = genai.GenerativeModel('gemini-pro')

from openai import OpenAI 
import os 
from dotenv import load_dotenv 
load_dotenv() 
client = OpenAI(api_key=os.environ['OPENAI_API_KEY']) 
r = client.embeddings.create(input='test', model='text-embedding-3-small') 
print('OK dims:', len(r.data[0].embedding)) 

Bookie  

Jaden Fiero  
Abigail Buckland  
Jose Gonzalez  
Collin Le  

Launch Instructions:  
Install python 3.1x and clone the repository  
Create a new .env file or rename the existing .env.example file
Get a google books API key from https://console.cloud.google.com and modify GOOGLE_BOOKS_API_KEY in .env to be the API key  
Get a gemini API key from https://aistudio.google.com/app/apikey and modify GEMINI_API_KEY in .env to be the API key  
Generate a 24 bye hex string (look it up) and modify FLASK_SECRET_KEY in .env to be the generated string
Run the following commands in the terminal in the directory containing app.py:  
pip install -r requirements.txt  
py app.py  

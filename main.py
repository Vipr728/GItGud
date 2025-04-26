from flask import Flask
import requests
import json
from github import Github
from dotenv import load_dotenv
load_dotenv()
import os
from transformers import AutoTokenizer, AutoModelForSequenceClassification

g = Github(os.getenv("ACCESS_TOKEN"))

app = Flask(__name__)

@app.route('/')
def get_user_repos(username):
    """Get repositories for a user using API"""
    user = g.get_user(username)
    repos = []
    
    for repo in user.get_repos():
        repo_data = {
            "name": repo.name,
            "stars": repo.stargazers_count,
            "languages": repo.get_languages(),
            "description": repo.description,
            "url": repo.html_url
        }
        repos.append(repo_data)
    
    return repos

# Load the AI model for vulnerability detection
def load_ai_model():
    model_name = "your-model-name"  # Replace with your model's name or path
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    return tokenizer, model

def analyze_code_for_vulnerabilities(file_path, tokenizer, model):
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()

    # Tokenize the code
    inputs = tokenizer(code, return_tensors="pt", truncation=True, max_length=512)

    # Run the model
    outputs = model(**inputs)
    predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)

    # Interpret the results (assuming binary classification: 0 = safe, 1 = vulnerable)
    vulnerability_score = predictions[0][1].item()
    return vulnerability_score

def download_repo_contents(username, repo_name):
    repo = g.get_repo(f"{username}/{repo_name}")

    # Create a special downloads folder
    downloads_folder = "downloads"
    os.makedirs(downloads_folder, exist_ok=True)

    # Load the AI model
    tokenizer, model = load_ai_model()

    # Get all files recursively
    contents = repo.get_contents("")

    while contents:
        file_content = contents.pop(0)
        if file_content.type == "dir":
            contents.extend(repo.get_contents(file_content.path))
        else:
            # Handle root-level files
            directory = os.path.join(downloads_folder, os.path.dirname(file_content.path))
            if directory:  # Only create directories if the path is not empty
                os.makedirs(directory, exist_ok=True)

            # Download file
            file_path = os.path.join(downloads_folder, file_content.path)
            with open(file_path, "wb") as f:
                f.write(file_content.decoded_content)

            # Analyze the file for vulnerabilities
            if file_path.endswith(".py") or file_path.endswith(".js") or file_path.endswith(".java"):
                vulnerability_score = analyze_code_for_vulnerabilities(file_path, tokenizer, model)
                print(f"Vulnerability score for {file_path}: {vulnerability_score}")

    print(f"Downloaded {repo_name} successfully into {downloads_folder}")

# Usage
repos = get_user_repos("floatedbloom")
with open("repos.json", "w") as f:
    json.dump(repos, f, indent=2)

# Download contents for each repository
for repo in repos:
    download_repo_contents("floatedbloom", repo['name'])
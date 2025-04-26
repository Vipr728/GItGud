from flask import Flask
import requests
import json
from github import Github
from dotenv import load_dotenv
load_dotenv()
import os

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

def download_repo_contents(username, repo_name):
    repo = g.get_repo(f"{username}/{repo_name}")
    
    # Get all files recursively
    contents = repo.get_contents("")
    
    while contents:
        file_content = contents.pop(0)
        if file_content.type == "dir":
            contents.extend(repo.get_contents(file_content.path))
        else:
            # Create directory structure
            os.makedirs(os.path.dirname(file_content.path), exist_ok=True)
            
            # Download file
            with open(file_content.path, "wb") as f:
                f.write(file_content.decoded_content)
                
    print(f"Downloaded {repo_name} successfully")

# Usage
repos = get_user_repos("torvalds")
with open("repos.json", "w") as f:
    json.dump(repos, f, indent=2)
download_repo_contents("torvalds", (repo['name'] for repo in repos))

#who, what where how why when
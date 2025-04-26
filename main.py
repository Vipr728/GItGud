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

    # Create a special downloads folder
    downloads_folder = "downloads"
    os.makedirs(downloads_folder, exist_ok=True)

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

    print(f"Downloaded {repo_name} successfully into {downloads_folder}")

# Usage
repos = get_user_repos("floatedbloom")
with open("repos.json", "w") as f:
    json.dump(repos, f, indent=2)

# Download contents for each repository
for repo in repos:
    download_repo_contents("floatedbloom", repo['name'])
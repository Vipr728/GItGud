from flask import Flask
import requests
import json
from github import Github
from dotenv import load_dotenv
import os
from openai import OpenAI

# Load API keys
load_dotenv()
APIKEY = os.getenv("NVIDIA_NIM_API_KEY_EFFICIENCY")

g = Github(os.getenv("ACCESS_TOKEN"))

app = Flask(__name__)

@app.route('/')
def get_user_repos(username):
    """Get the 5 repositories with the most commits for a user using the API"""
    user = g.get_user(username)
    repos = []

    for repo in user.get_repos():
        try:
            # Get the number of commits for the repository
            commit_count = repo.get_commits().totalCount
            repo_data = {
                "name": repo.name,
                "stars": repo.stargazers_count,
                "languages": repo.get_languages(),
                "description": repo.description,
                "url": repo.html_url,
                "commit_count": commit_count
            }
            repos.append(repo_data)
        except Exception as e:
            if "Git Repository is empty" in str(e):
                print(f"Repository {repo.name} is empty. Creating a placeholder.")
                # Create a placeholder for empty repositories
                placeholder_folder = os.path.join("downloads", repo.name)
                os.makedirs(placeholder_folder, exist_ok=True)
                placeholder_file = os.path.join(placeholder_folder, "placeholder.txt")
                with open(placeholder_file, "w") as f:
                    f.write("")
            else:
                print(f"Error fetching commits for {repo.name}: {e}")

    # Sort by commit_count and get the top 5
    repos = sorted(repos, key=lambda x: x["commit_count"], reverse=True)[:5]
    return repos

def analyze_code_for_vulnerabilities(file_path):
    """Analyze the given code file for vulnerabilities using DeepSeek AI."""
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=APIKEY,
    )

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()

        completion = client.chat.completions.create(
            model="deepseek-ai/deepseek-r1-distill-qwen-7b",
            messages=[
                {"role": "user", "content": f"Analyze the vulnerabilities of the following code:\n{code}"}
            ],
            temperature=0.6,
            top_p=0.7,
            max_tokens=4096,
            stream=False
        )

        # Extract the response content
        response = completion.choices[0].message.content
        return response

    except Exception as e:
        print(f"Error analyzing vulnerabilities: {e}")
        return "Error occurred during analysis."

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
            directory = os.path.join(downloads_folder, repo_name, os.path.dirname(file_content.path))
            if directory:  # Only create directories if the path is not empty
                os.makedirs(directory, exist_ok=True)

            # Download file
            file_path = os.path.join(downloads_folder, repo_name, file_content.path)
            with open(file_path, "wb") as f:
                f.write(file_content.decoded_content)

            # Analyze the file for vulnerabilities
            if file_path.endswith(".py") or file_path.endswith(".js") or file_path.endswith(".java"):
                vulnerability_score = analyze_code_for_vulnerabilities(file_path)
                print(f"Vulnerability analysis for {file_path}:\n{vulnerability_score}")

            # Pass the file to the efficiency chatbot
            from utils.efficency import evaluate_efficiency
            with open(file_path, "r", encoding="utf-8") as code_file:
                code_content = code_file.read()
                efficiency_score = evaluate_efficiency(code_content)
                print(f"Efficiency analysis for {file_path}:\n{efficiency_score}")

    print(f"Downloaded {repo_name} successfully into {downloads_folder}")

# Usage
repos = get_user_repos("floatedbloom")
with open("repos.json", "w") as f:
    json.dump(repos, f, indent=2)

# Download contents for each repository
for repo in repos:
    download_repo_contents("floatedbloom", repo['name'])
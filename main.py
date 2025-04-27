from flask import Flask, render_template, request
import requests
import json
from github import Github
from dotenv import load_dotenv
import os
from openai import OpenAI
from utils.efficency import evaluate_efficiency
from utils.security import evaluate_security
from utils.quality import evaluate_quality
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Load API keys
load_dotenv()
APIKEY = os.getenv("NVIDIA_NIM_API_KEY_EFFICIENCY")

g = Github(os.getenv("ACCESS_TOKEN"))

app = Flask(__name__)

# Add a simple cache for repository analysis results
repo_cache = {}
user_cache = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form['username']
        return analyze_and_display_repos(username)
    elif request.method == 'GET' and 'username' in request.args:
        username = request.args.get('username')
        return analyze_and_display_repos(username)

    return render_template('index.html', results=None)

def analyze_and_display_repos(username):
    """Common function to analyze repos and return results for both GET and POST requests"""
    try:
        # Check if we have cached results for this user
        if username in user_cache:
            print(f"Using cached results for {username}")
            return render_template('index.html', results=user_cache[username], username=username)
            
        # Add timeout to prevent hanging on user fetch
        repos = get_user_repos(username, timeout=300)  # 5 minutes timeout for repo fetching
        if not repos:
            return render_template('index.html', error=f"No repositories found for user {username}")
            
        # Create a ThreadPoolExecutor to analyze repos in parallel
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Submit all repo analysis tasks
            future_to_repo = {executor.submit(analyze_repo, username, repo): repo for repo in repos}
            
            # Process results as they complete
            for future in future_to_repo:
                repo = future_to_repo[future]
                try:
                    repo_results = future.result(timeout=300)  # 5-minute timeout per repo
                    results.append(repo_results)
                except Exception as e:
                    print(f"Error analyzing repository {repo['name']}: {e}")
                    results.append({
                        'name': repo['name'],
                        'security': {'score': 'Error', 'concerns': [str(e)]},
                        'efficiency': {'score': 'Error', 'concerns': [str(e)]},
                        'quality': {'score': 'Error', 'concerns': [str(e)]},
                        'description': repo.get('description', ''),
                        'languages': repo.get('languages', {}),
                        'url': repo.get('url', '')
                    })
        
        # Calculate overall ELO scores for each repo
        for repo in results:
            scores = []
            for metric in ['security', 'efficiency', 'quality']:
                try:
                    if repo[metric]['score'] not in ['N/A', 'Error']:
                        scores.append(float(repo[metric]['score']))
                except (ValueError, KeyError):
                    pass
            
            # Set overall score
            if scores:
                repo['overall_score'] = sum(scores) / len(scores)
            else:
                repo['overall_score'] = 'N/A'
        
        # Cache results for future use
        user_cache[username] = results
        
        return render_template('index.html', results=results, username=username)
    except Exception as e:
        return render_template('index.html', error=f"Error: {str(e)}")

def get_user_repos(username, timeout=30, limit=None):
    """Get repositories for a user using the API, with optional limit"""
    try:
        user = g.get_user(username)
        repos = []

        import time
        start_time = time.time()
        
        for repo in user.get_repos():
            # Check timeout
            if time.time() - start_time > timeout:
                print(f"Timeout reached when fetching repos for {username}")
                break
                
            try:
                # Get the number of commits for the repository with a small timeout
                commit_count = 0
                try:
                    # Try to get commit count with timeout
                    commit_count = repo.get_commits().totalCount
                except Exception as commit_error:
                    print(f"Error getting commits for {repo.name}: {commit_error}")
                    commit_count = 0
                
                repo_data = {
                    "name": repo.name,
                    "stars": repo.stargazers_count,
                    "languages": repo.get_languages(),
                    "description": repo.description,
                    "url": repo.html_url,
                    "commit_count": commit_count
                }
                repos.append(repo_data)
                
                # If we have reached the limit, break early
                if limit and len(repos) >= limit:
                    break
            except Exception as e:
                print(f"Error fetching repo {repo.name}: {e}")

        # Sort by stars if commit count is not reliable
        if not any(r["commit_count"] > 0 for r in repos) and repos:
            repos = sorted(repos, key=lambda x: x["stars"], reverse=True)
        else:
            repos = sorted(repos, key=lambda x: x["commit_count"], reverse=True)
            
        # Apply limit if specified
        if limit:
            repos = repos[:limit]
            
        return repos
    except Exception as e:
        print(f"Error in get_user_repos: {e}")
        return []

def analyze_repo(username, repo):
    """Analyze a single repository with sampling to speed up processing"""
    # Check if we already have cached results for this repo
    if username in repo_cache and repo['name'] in repo_cache[username]:
        print(f"Using cached analysis for {username}/{repo['name']}")
        return repo_cache[username][repo['name']]
    
    repo_results = {
        'name': repo['name'],
        'security': {'score': 'N/A', 'concerns': []},
        'efficiency': {'score': 'N/A', 'concerns': []},
        'quality': {'score': 'N/A', 'concerns': []},
        'description': repo.get('description', ''),
        'languages': repo.get('languages', {}),
        'url': repo.get('url', '')
    }
    
    try:
        # Get repo contents with timeout protection
        repo_obj = g.get_repo(f"{username}/{repo['name']}")
        
        try:
            contents = repo_obj.get_contents("")
        except Exception as e:
            if "Git Repository is empty" in str(e):
                print(f"Repository {repo['name']} is empty. Skipping analysis.")
                return repo_results
            raise
            
        # Sample files: collect up to 5 files of each supported type
        sample_files = []
        directories = []
        file_extensions = (".py", ".js", ".java", ".cpp", ".c", ".ts", ".dart", ".swift", ".kt", ".html", ".css", ".m", ".h", ".cs")
        
        # Files per extension counter
        extension_counts = {ext: 0 for ext in file_extensions}
        max_files_per_ext = 3  # Increased from 2
        max_total_files = 15   # Increased from 10
        
        # Safety counter to prevent infinite loop
        safety_counter = 0
        max_iterations = 2000  # Increased from 1000
        
        while contents and len(sample_files) < max_total_files and safety_counter < max_iterations:
            safety_counter += 1
            file_content = contents.pop(0)
            
            if file_content.type == "dir":
                try:
                    # Get directory contents
                    directories.append(file_content.path)
                    if len(directories) <= 10:  # Increased from 5
                        dir_contents = repo_obj.get_contents(file_content.path)
                        if isinstance(dir_contents, list):
                            contents.extend(dir_contents[:10])  # Increased from 5
                except Exception as dir_error:
                    print(f"Error exploring directory {file_content.path}: {dir_error}")
            elif file_content.path.endswith(file_extensions):
                ext = next((e for e in file_extensions if file_content.path.endswith(e)), None)
                if ext and extension_counts[ext] < max_files_per_ext:
                    try:
                        code_content = file_content.decoded_content.decode("utf-8")
                        sample_files.append((file_content.path, code_content))
                        extension_counts[ext] += 1
                    except Exception as decode_error:
                        print(f"Error decoding {file_content.path}: {decode_error}")
        
        # Analyze sampled files in parallel
        if sample_files:
            security_results = []
            efficiency_results = []
            quality_results = []
            
            with ThreadPoolExecutor(max_workers=5) as executor:  # Reduced from 10
                # Submit security, efficiency, and quality analysis in parallel
                future_to_file = {}
                for path, content in sample_files:
                    future_to_file[executor.submit(evaluate_security, content, path)] = f"{path}_security"
                    future_to_file[executor.submit(evaluate_efficiency, content, path)] = f"{path}_efficiency"
                    future_to_file[executor.submit(evaluate_quality, content, path)] = f"{path}_quality"
                
                # Process results as they complete
                for future in future_to_file:
                    task_id = future_to_file[future]
                    try:
                        result = future.result(timeout=300)  # 5-minute timeout (increased from 20 seconds)
                        if task_id.endswith("_security"):
                            security_results.append(result)
                        elif task_id.endswith("_efficiency"):
                            efficiency_results.append(result)
                        elif task_id.endswith("_quality"):
                            quality_results.append(result)
                    except Exception as analysis_error:
                        print(f"Error in analysis task {task_id}: {analysis_error}")
            
            # Process security results
            if security_results:
                # Aggregate all concerns
                all_concerns = []
                for result in security_results:
                    if isinstance(result, dict) and 'concerns' in result:
                        all_concerns.extend(result.get('concerns', []))
                    
                # Get unique concerns (limit to top 5)
                unique_concerns = []
                for concern in all_concerns:
                    if concern not in unique_concerns and concern not in ["Unable to analyze code", "Analysis timed out", "No specific concerns identified"]:
                        unique_concerns.append(concern)
                        if len(unique_concerns) >= 5:
                            break
                
                # Calculate average score
                scores = []
                for result in security_results:
                    if isinstance(result, dict) and 'score' in result:
                        try:
                            score = float(result['score'])
                            scores.append(score)
                        except (ValueError, TypeError):
                            pass
                
                avg_score = sum(scores) / len(scores) if scores else 50
                repo_results['security'] = {
                    'score': str(avg_score),
                    'concerns': unique_concerns
                }
            
            # Process efficiency results
            if efficiency_results:
                # Aggregate all concerns
                all_concerns = []
                for result in efficiency_results:
                    if isinstance(result, dict) and 'concerns' in result:
                        all_concerns.extend(result.get('concerns', []))
                    
                # Get unique concerns (limit to top 5)
                unique_concerns = []
                for concern in all_concerns:
                    if concern not in unique_concerns and concern not in ["Unable to analyze code", "Analysis timed out", "No specific concerns identified"]:
                        unique_concerns.append(concern)
                        if len(unique_concerns) >= 5:
                            break
                
                # Calculate average score
                scores = []
                for result in efficiency_results:
                    if isinstance(result, dict) and 'score' in result:
                        try:
                            score = float(result['score'])
                            scores.append(score)
                        except (ValueError, TypeError):
                            pass
                
                avg_score = sum(scores) / len(scores) if scores else 50
                repo_results['efficiency'] = {
                    'score': str(avg_score),
                    'concerns': unique_concerns
                }
            
            # Process quality results
            if quality_results:
                # Aggregate all concerns
                all_concerns = []
                for result in quality_results:
                    if isinstance(result, dict) and 'concerns' in result:
                        all_concerns.extend(result.get('concerns', []))
                    
                # Get unique concerns (limit to top 5)
                unique_concerns = []
                for concern in all_concerns:
                    if concern not in unique_concerns and concern not in ["Unable to analyze code", "Analysis timed out", "No specific concerns identified"]:
                        unique_concerns.append(concern)
                        if len(unique_concerns) >= 5:
                            break
                
                # Calculate average score
                scores = []
                for result in quality_results:
                    if isinstance(result, dict) and 'score' in result:
                        try:
                            score = float(result['score'])
                            scores.append(score)
                        except (ValueError, TypeError):
                            pass
                
                avg_score = sum(scores) / len(scores) if scores else 50
                repo_results['quality'] = {
                    'score': str(avg_score),
                    'concerns': unique_concerns
                }
    
    except Exception as e:
        print(f"Error analyzing repository {repo['name']}: {e}")
    
    # Cache the results
    if username not in repo_cache:
        repo_cache[username] = {}
    repo_cache[username][repo['name']] = repo_results
    
    return repo_results

def download_repo_contents(username, repo_name):
    repo = g.get_repo(f"{username}/{repo_name}")

    # Get all files recursively
    try:
        contents = repo.get_contents("")
    except Exception as e:
        if "Git Repository is empty" in str(e):
            print(f"Repository {repo_name} is empty. Creating a placeholder.")
            placeholder_folder = os.path.join("downloads", repo_name)
            os.makedirs(placeholder_folder, exist_ok=True)
            placeholder_file = os.path.join(placeholder_folder, "placeholder.txt")
            with open(placeholder_file, "w") as f:
                f.write("")
            return  # Exit early for empty repositories
        else:
            raise e

    while contents:
        print ('infinite loop')
        file_content = contents.pop(0)
        if file_content.type == "dir":
            contents.extend(repo.get_contents(file_content.path))
        else:
            # Only process code files with specific extensions
            if file_content.path.endswith((".py", ".js", ".java", ".cpp", ".c", ".ts")):
                # Fetch file content directly from GitHub
                code_content = file_content.decoded_content.decode("utf-8")

                # SECURITY ANALYSIS
                vulnerability_score = evaluate_security(code_content)
                print(f"Vulnerability analysis for {file_content.path}:{vulnerability_score}")

                # EFFICIENCY ANALYSIS                
                efficiency_score = evaluate_efficiency(code_content)
                print(f"Efficiency analysis for {file_content.path}:{efficiency_score}")

                # QUALITY ANALYSIS
                #quality_score = evaluate_quality(code_content)
                #print(f"quality analysis for {file_content.path}:{quality_score}")

    print(f"Analyzed {repo_name} successfully without downloading files.")

def analyze_file_concurrently(file_content, username, repo_name):
    """Analyze a single file concurrently for security, efficiency, and quality."""
    code_content = file_content.decoded_content.decode("utf-8")

    # SECURITY ANALYSIS
    security_score = evaluate_security(code_content)

    # EFFICIENCY ANALYSIS
    efficiency_score = evaluate_efficiency(code_content)

    # QUALITY ANALYSIS
    quality_score = 50 #evaluate_quality(code_content)

    return {
        "file_path": file_content.path,
        "security": security_score,
        "efficiency": efficiency_score,
        "quality": quality_score
    }

async def analyze_repo_concurrently(username, repo_name):
    try:
        repo = g.get_repo(f"{username}/{repo_name}")
        contents = repo.get_contents("")
        tasks = []

        with ThreadPoolExecutor() as executor:
            while contents:
                file_content = contents.pop(0)
                if file_content.type == "dir":
                    contents.extend(repo.get_contents(file_content.path))
                elif file_content.path.endswith((".py", ".js", ".java", ".cpp", ".c", ".ts")):
                    # Schedule analysis for each file
                    loop = asyncio.get_event_loop()
                    tasks.append(loop.run_in_executor(executor, analyze_file_concurrently, file_content, username, repo_name))

            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks)
        
        return results
    except Exception as e:
        if "Git Repository is empty" in str(e):
            print(f"Repository {repo_name} is empty. Skipping analysis.")
            # Return empty result for empty repositories
            return []
        else:
            print(f"Error analyzing repository {repo_name}: {e}")
            return []

@app.route('/analyze', methods=['POST'])
def analyze():
    username = request.form['username']
    repos = get_user_repos(username)
    all_results = []

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for repo in repos:
        try:
            results = loop.run_until_complete(analyze_repo_concurrently(username, repo['name']))
            # Format results for display
            formatted_results = {
                'name': repo['name'],
                'security': 'N/A',
                'efficiency': 'N/A',
                'quality': 'N/A'
            }
            
            # Calculate averages if there are results
            if results:
                security_scores = []
                efficiency_scores = []
                quality_scores = []
                
                for result in results:
                    try:
                        sec_score = result.get('security', 'N/A')
                        if isinstance(sec_score, str) and not sec_score.isdigit():
                            security_scores.append(50)
                        else:
                            security_scores.append(int(sec_score))
                            
                        eff_score = result.get('efficiency', 'N/A')
                        if isinstance(eff_score, str) and not eff_score.isdigit():
                            efficiency_scores.append(50)
                        else:
                            efficiency_scores.append(int(eff_score))
                            
                        qual_score = result.get('quality', 'N/A')
                        if isinstance(qual_score, str) and not qual_score.isdigit():
                            quality_scores.append(50)
                        else:
                            quality_scores.append(int(qual_score))
                    except (ValueError, TypeError):
                        # Use default values if conversion fails
                        security_scores.append(50)
                        efficiency_scores.append(50)
                        quality_scores.append(50)
                
                # Calculate final scores
                formatted_results['security'] = sum(security_scores) / len(security_scores) if security_scores else 'N/A'
                formatted_results['efficiency'] = sum(efficiency_scores) / len(efficiency_scores) if efficiency_scores else 'N/A'
                formatted_results['quality'] = sum(quality_scores) / len(quality_scores) if quality_scores else 'N/A'
            
            all_results.append(formatted_results)
        except Exception as e:
            print(f"Error analyzing repository {repo['name']}: {e}")
            all_results.append({
                'name': repo['name'],
                'security': 'Error',
                'efficiency': 'Error',
                'quality': 'Error'
            })

    loop.close()

    return render_template('index.html', results=all_results, username=username)

@app.route('/repo/<username>/<repo_name>')
def repo_details(username, repo_name):
    """Route to display detailed repository analysis"""
    try:
        # Check if this repo is already in the cache
        if username in user_cache:
            cached_results = user_cache[username]
            for repo in cached_results:
                if repo['name'] == repo_name:
                    return render_template('repo_details.html', repo=repo, username=username)
        
        # If not in cache, get the repository data
        repo = next((r for r in get_user_repos(username) if r['name'] == repo_name), None)
        
        if not repo:
            return render_template('error.html', error=f"Repository {repo_name} not found")
        
        # Analyze the repository
        result = analyze_repo(username, repo)
        
        # Calculate overall score
        scores = []
        for metric in ['security', 'efficiency', 'quality']:
            try:
                if result[metric]['score'] not in ['N/A', 'Error']:
                    scores.append(float(result[metric]['score']))
            except (ValueError, KeyError):
                pass
        
        if scores:
            result['overall_score'] = sum(scores) / len(scores)
        else:
            result['overall_score'] = 'N/A'
        
        # Cache the result
        if username not in repo_cache:
            repo_cache[username] = {}
        repo_cache[username][repo_name] = result
        
        return render_template('repo_details.html', repo=result, username=username)
    except Exception as e:
        return render_template('error.html', error=f"Error analyzing repository: {str(e)}")

@app.route('/readme-badge/<username>')
def generate_readme_badge(username):
    """Generate a GitHub README badge with GitHub Doctor scores"""
    try:
        # Check if user is in cache
        if username not in user_cache:
            return render_template('error.html', error=f"User {username} not found. Please analyze their repositories first.")
        
        results = user_cache[username]
        
        # Calculate average scores across all repositories
        security_scores = []
        efficiency_scores = []
        quality_scores = []
        overall_scores = []
        
        for repo in results:
            try:
                if repo['security']['score'] not in ['N/A', 'Error']:
                    security_scores.append(float(repo['security']['score']))
                if repo['efficiency']['score'] not in ['N/A', 'Error']:
                    efficiency_scores.append(float(repo['efficiency']['score']))
                if repo['quality']['score'] not in ['N/A', 'Error']:
                    quality_scores.append(float(repo['quality']['score']))
                if repo.get('overall_score') not in ['N/A', 'Error']:
                    overall_scores.append(float(repo['overall_score']))
            except (ValueError, KeyError):
                pass
        
        # Calculate averages
        avg_security = sum(security_scores) / len(security_scores) if security_scores else 'N/A'
        avg_efficiency = sum(efficiency_scores) / len(efficiency_scores) if efficiency_scores else 'N/A'
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 'N/A'
        avg_overall = sum(overall_scores) / len(overall_scores) if overall_scores else 'N/A'
        
        # Prepare data for the template
        badge_data = {
            'username': username,
            'security': round(avg_security) if avg_security != 'N/A' else 'N/A',
            'efficiency': round(avg_efficiency) if avg_efficiency != 'N/A' else 'N/A',
            'quality': round(avg_quality) if avg_quality != 'N/A' else 'N/A',
            'overall': round(avg_overall) if avg_overall != 'N/A' else 'N/A',
        }
        
        return render_template('readme_badge.html', badge=badge_data)
        
    except Exception as e:
        return render_template('error.html', error=f"Error generating README badge: {str(e)}")

@app.route('/user-report/<username>')
def user_report(username):
    """Generate a comprehensive GitHub report with stats, common errors, and recommendations"""
    try:
        # Check if user is in cache
        if username not in user_cache:
            return render_template('error.html', error=f"User {username} not found. Please analyze their repositories first.")
        
        results = user_cache[username]
        
        # Calculate average scores across all repositories
        security_scores = []
        efficiency_scores = []
        quality_scores = []
        overall_scores = []
        
        # Collect all concerns for analysis
        all_security_concerns = []
        all_efficiency_concerns = []
        all_quality_concerns = []
        
        for repo in results:
            try:
                # Collect scores
                if repo['security']['score'] not in ['N/A', 'Error']:
                    security_scores.append(float(repo['security']['score']))
                if repo['efficiency']['score'] not in ['N/A', 'Error']:
                    efficiency_scores.append(float(repo['efficiency']['score']))
                if repo['quality']['score'] not in ['N/A', 'Error']:
                    quality_scores.append(float(repo['quality']['score']))
                if repo.get('overall_score') not in ['N/A', 'Error']:
                    overall_scores.append(float(repo['overall_score']))
                
                # Collect concerns
                all_security_concerns.extend(repo['security'].get('concerns', []))
                all_efficiency_concerns.extend(repo['efficiency'].get('concerns', []))
                all_quality_concerns.extend(repo['quality'].get('concerns', []))
            except (ValueError, KeyError):
                pass
        
        # Calculate averages
        avg_security = sum(security_scores) / len(security_scores) if security_scores else 'N/A'
        avg_efficiency = sum(efficiency_scores) / len(efficiency_scores) if efficiency_scores else 'N/A'
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 'N/A'
        avg_overall = sum(overall_scores) / len(overall_scores) if overall_scores else 'N/A'
        
        # Filter out "No concerns detected" messages
        all_security_concerns = [concern for concern in all_security_concerns if not "No security concerns detected" in concern]
        all_efficiency_concerns = [concern for concern in all_efficiency_concerns if not "No efficiency concerns detected" in concern]
        all_quality_concerns = [concern for concern in all_quality_concerns if not "No quality concerns detected" in concern]
        
        # Get frequency of each concern
        from collections import Counter
        
        security_counter = Counter(all_security_concerns)
        efficiency_counter = Counter(all_efficiency_concerns)
        quality_counter = Counter(all_quality_concerns)
        
        # Get top 5 most common concerns
        top_security_concerns = security_counter.most_common(5)
        top_efficiency_concerns = efficiency_counter.most_common(5)
        top_quality_concerns = quality_counter.most_common(5)
        
        # Define help resources
        security_resources = [
            {"title": "OWASP Top Ten", "url": "https://owasp.org/www-project-top-ten/"},
            {"title": "Web Security Academy", "url": "https://portswigger.net/web-security"},
            {"title": "Security Best Practices", "url": "https://cheatsheetseries.owasp.org/"}
        ]
        
        efficiency_resources = [
            {"title": "Performance Best Practices", "url": "https://web.dev/performance-optimizing-content-efficiency/"},
            {"title": "Algorithmic Complexity Guide", "url": "https://www.bigocheatsheet.com/"},
            {"title": "Code Optimization Techniques", "url": "https://github.com/donnemartin/system-design-primer"}
        ]
        
        quality_resources = [
            {"title": "Clean Code Principles", "url": "https://github.com/ryanmcdermott/clean-code-javascript"},
            {"title": "Code Review Best Practices", "url": "https://google.github.io/eng-practices/review/"},
            {"title": "Refactoring Techniques", "url": "https://refactoring.com/catalog/"}
        ]
        
        # Prepare data for the template
        report_data = {
            'username': username,
            'security': {
                'score': round(avg_security) if avg_security != 'N/A' else 'N/A',
                'top_concerns': top_security_concerns,
                'resources': security_resources
            },
            'efficiency': {
                'score': round(avg_efficiency) if avg_efficiency != 'N/A' else 'N/A',
                'top_concerns': top_efficiency_concerns,
                'resources': efficiency_resources
            },
            'quality': {
                'score': round(avg_quality) if avg_quality != 'N/A' else 'N/A',
                'top_concerns': top_quality_concerns,
                'resources': quality_resources
            },
            'overall': round(avg_overall) if avg_overall != 'N/A' else 'N/A',
            'repo_count': len(results)
        }
        
        # Prepare badge data for README markdown
        badge_data = {
            'username': username,
            'security': round(avg_security) if avg_security != 'N/A' else 'N/A',
            'efficiency': round(avg_efficiency) if avg_efficiency != 'N/A' else 'N/A',
            'quality': round(avg_quality) if avg_quality != 'N/A' else 'N/A',
            'overall': round(avg_overall) if avg_overall != 'N/A' else 'N/A',
        }
        
        return render_template('user_report.html', report=report_data, badge=badge_data)
        
    except Exception as e:
        return render_template('error.html', error=f"Error generating user report: {str(e)}")

# Ensure non-Flask logic is executed only when not running the Flask app
if __name__ == "__main__":
    app.run(debug=True)
    if "FLASK_RUN" not in os.environ:  # Check if Flask is running
        repos = get_user_repos("floatedbloom")
        with open("repos.json", "w") as f:
            json.dump(repos, f, indent=2)

        # Download contents for each repository
        for repo in repos:
            download_repo_contents("floatedbloom", repo['name'])
    else:
        app.run(debug=True)
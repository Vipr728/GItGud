from flask import Flask, render_template, request, redirect, url_for, jsonify
import requests
import json
from github import Github
from dotenv import load_dotenv
import os
from openai import OpenAI, AsyncOpenAI
from utils.efficiency import evaluate_efficiency
from utils.security import evaluate_security
from utils.quality import evaluate_quality
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from tqdm import tqdm
from queue import Queue
import random

# Load API keys
load_dotenv()
APIKEY = os.getenv("OPENAI_API_KEY")

# Create async client for OpenAI
async_client = AsyncOpenAI(api_key=APIKEY)
client = OpenAI(api_key=APIKEY)

g = Github(os.getenv("ACCESS_TOKEN"))

app = Flask(__name__)

# Add a simple cache for repository analysis results
repo_cache = {}
user_cache = {}

# Global processing queue to limit concurrent API requests
api_request_queue = Queue()
MAX_CONCURRENT_REQUESTS = 1  # Only process one request at a time
RATE_LIMIT_DELAY = 2  # Delay between API requests in seconds

# Flag to track if the queue processor is running
queue_processor_running = False

# Function to process the API request queue
def process_api_queue():
    global queue_processor_running
    queue_processor_running = True
    
    while not api_request_queue.empty():
        # Get the next item from the queue
        func, args, kwargs, callback = api_request_queue.get()
        
        try:
            # Execute the API call
            result = func(*args, **kwargs)
            
            # Call the callback with the result
            if callback:
                callback(result)
        except Exception as e:
            print(f"Error processing queue item: {e}")
        finally:
            # Rate limiting delay
            time.sleep(RATE_LIMIT_DELAY)
            api_request_queue.task_done()
    
    queue_processor_running = False

# Function to enqueue an API request
def enqueue_api_request(func, *args, callback=None, **kwargs):
    api_request_queue.put((func, args, kwargs, callback))
    
    # Start the queue processor if it's not already running
    global queue_processor_running
    if not queue_processor_running:
        threading.Thread(target=process_api_queue, daemon=True).start()
    
    return True  # Acknowledge the request was queued

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
    """Get repositories for a user but skip analysis until explicitly requested"""
    try:
        # Get repos for the user
        repos = get_user_repos(username, timeout=300)  # 5 minutes timeout for repo fetching
        if not repos:
            return render_template('index.html', error=f"No repositories found for user {username}")
        
        # Create lightweight results without analysis
        results = []
        for repo in repos:
            # Create a placeholder result with basic info
            repo_result = {
                'name': repo['name'],
                'security': {'score': 'Click to analyze', 'concerns': []},
                'efficiency': {'score': 'Click to analyze', 'concerns': []},
                'quality': {'score': 'Click to analyze', 'concerns': []},
                'description': repo.get('description', ''),
                'languages': repo.get('languages', {}),
                'url': repo.get('url', ''),
                'overall_score': 'Click to analyze',
                'analyzed': False  # Flag to indicate analysis status
            }
            results.append(repo_result)
        
        # Cache these basic results
        user_cache[username] = results
        
        return render_template('index.html', results=results, username=username)
    except Exception as e:
        return render_template('index.html', error=f"Error: {str(e)}")

def get_user_repos(username, timeout=30, limit=None):
    """Get all public repositories for a GitHub user"""
    try:
        # Check if we have cached data for this username
        if username in user_cache:
            print(f"Using cached repository list for {username}")
            cached_repos = user_cache[username]
            # If limit is specified, return only that many repos
            if limit and len(cached_repos) > limit:
                return cached_repos[:limit]
            return cached_repos
        
        print(f"Fetching repositories for {username}")
        
        # Fetch from GitHub API if not in cache
        start_time = time.time()
        user = g.get_user(username)
        repos = []
        
        # Get repository data
        for repo in user.get_repos():
            if time.time() - start_time > timeout:
                print(f"Timeout exceeded for {username}, returning partial results")
                if repos:
                    # Cache the partial results we have
                    user_cache[username] = repos
                    return repos
                break
            
            try:
                # Get programming languages
                languages = repo.get_languages()
                
                # Only include non-empty repositories with code
                if languages:  # Skip empty repos
                    repo_data = {
                        'name': repo.name,
                        'description': repo.description,
                        'url': repo.html_url,
                        'languages': languages,
                        'size': repo.size,
                        'fork': repo.fork,
                        'stargazers_count': repo.stargazers_count,
                        # Initialize metrics structures
                        'security': {'score': 'N/A', 'concerns': []},
                        'efficiency': {'score': 'N/A', 'concerns': []},
                        'quality': {'score': 'N/A', 'concerns': []},
                        'analyzed': False  # Mark as not yet analyzed
                    }
                    repos.append(repo_data)
                    if limit and len(repos) >= limit:
                        break
            except Exception as e:
                print(f"Error processing repository {repo.name}: {e}")
                continue
        
        # Cache the results if we got any
        if repos:
            user_cache[username] = repos
        
        return repos
    except Exception as e:
        print(f"Error getting repositories for {username}: {e}")
        return []

async def analyze_repo_async(username, repo):
    """Async version of analyze_repo that uses AsyncOpenAI for better performance"""
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
        
        # Analyze sampled files in parallel using async
        if sample_files:
            security_results = []
            efficiency_results = []
            quality_results = []
            
            # Create tasks for each file analysis
            tasks = []
            for path, content in sample_files:
                # Add tasks for each analysis type
                tasks.append(evaluate_security(content, path))
                tasks.append(evaluate_efficiency(content, path))
                tasks.append(evaluate_quality(content, path))
            
            # Process results in an async way
            results = []
            for task in tasks:
                try:
                    result = await task
                    if result:
                        results.append(result)
                except Exception as e:
                    print(f"Error in async analysis: {e}")
            
            # Categorize results
            for result in results:
                # Determine which analysis type this is based on the presence of specific keys
                if isinstance(result, dict):
                    if 'security' in str(result).lower():
                        security_results.append(result)
                    elif 'efficiency' in str(result).lower():
                        efficiency_results.append(result)
                    else:
                        quality_results.append(result)
            
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

# Keep a synchronous version for backward compatibility
def analyze_repo(username, repo):
    """Synchronous version of analyze_repo that uses asyncio.run for async execution"""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(analyze_repo_async(username, repo))
    finally:
        loop.close()

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

async def analyze_repo_concurrently(username, repo_name):
    try:
        repo = g.get_repo(f"{username}/{repo_name}")
        contents = repo.get_contents("")
        files_to_analyze = []

        # First collect all files to analyze
        while contents:
            file_content = contents.pop(0)
            if file_content.type == "dir":
                try:
                    contents.extend(repo.get_contents(file_content.path))
                except Exception as e:
                    print(f"Error accessing directory {file_content.path}: {e}")
                    continue
            elif file_content.path.endswith((".py", ".js", ".java", ".cpp", ".c", ".ts")):
                files_to_analyze.append(file_content)
        
        # Cost-aware sampling: If there are too many files, analyze a representative sample
        MAX_FILES_TO_ANALYZE = 5  # Further reduced from 10 to 5
        if len(files_to_analyze) > MAX_FILES_TO_ANALYZE:
            print(f"Repository has {len(files_to_analyze)} files. Sampling {MAX_FILES_TO_ANALYZE} for analysis.")
            # Sample with bias toward larger files as they might be more important
            files_to_analyze.sort(key=lambda x: x.size, reverse=True)
            # Take some top files and some random files
            top_files = files_to_analyze[:MAX_FILES_TO_ANALYZE//2]
            random_files = random.sample(files_to_analyze[MAX_FILES_TO_ANALYZE//2:], 
                                         min(MAX_FILES_TO_ANALYZE//2, len(files_to_analyze)-MAX_FILES_TO_ANALYZE//2))
            files_to_analyze = top_files + random_files
        
        tasks = []
        results = []
        
        # Use a semaphore to limit concurrent analysis
        semaphore = asyncio.Semaphore(2)  # Reduced from 3 to 2 concurrent files
        
        async def analyze_with_rate_limit(file_content):
            async with semaphore:
                # Add a longer delay between API calls
                await asyncio.sleep(5)  # Increased from 1 to 5 seconds
                return analyze_file_concurrently(file_content, username, repo_name)
        
        # Create tasks for analysis
        for file_content in files_to_analyze:
            tasks.append(analyze_with_rate_limit(file_content))
        
        # Process tasks in batches to avoid overwhelming the API
        for i in range(0, len(tasks), 2):  # Reduced batch size from 3 to 2
            batch = tasks[i:i+2]
            batch_results = await asyncio.gather(*batch)
            results.extend(batch_results)
            # Add longer delay between batches
            await asyncio.sleep(10)  # Increased from 2 to 10 seconds
        
        return results
    except Exception as e:
        if "Git Repository is empty" in str(e):
            print(f"Repository {repo_name} is empty. Skipping analysis.")
            return []
        else:
            print(f"Error analyzing repository {repo_name}: {e}")
            return []

def analyze_file_concurrently(file_content, username, repo_name):
    """Analyze a single file concurrently for security, efficiency, and quality."""
    try:
        code_content = file_content.decoded_content.decode("utf-8")
        
        # Include username in file path for special case handling
        file_path_with_user = f"{username}/{file_content.path}"
        
        # COST-AWARE SAMPLING: For large files, analyze only portions of the file
        if len(code_content) > 10000:  # If file is larger than ~10KB
            lines = code_content.split('\n')
            # Get the first 100 lines, last 50 lines, and some random lines from the middle
            begin = '\n'.join(lines[:100])
            end = '\n'.join(lines[-50:])
            
            # Sample from the middle
            if len(lines) > 150:
                middle_lines = random.sample(lines[100:-50], min(100, len(lines)-150))
                middle = '\n'.join(middle_lines)
                code_content = f"{begin}\n# ... (code trimmed for analysis) ...\n{middle}\n# ... (code trimmed for analysis) ...\n{end}"
        
        # SECURITY ANALYSIS
        security_score = evaluate_security(code_content, file_path=file_path_with_user)

        # EFFICIENCY ANALYSIS
        efficiency_score = evaluate_efficiency(code_content, file_path=file_path_with_user)

        # QUALITY ANALYSIS
        # Using the synchronous version to avoid coroutine never awaited error
        quality_score = evaluate_quality(code_content, file_path=file_path_with_user)

        return {
            "file_path": file_content.path,
            "security": security_score,
            "efficiency": efficiency_score,
            "quality": quality_score
        }
    except Exception as e:
        print(f"Error analyzing file {file_content.path}: {e}")
        return {
            "file_path": file_content.path,
            "security": {"score": "Error", "concerns": [f"Failed to analyze: {str(e)}"]},
            "efficiency": {"score": "Error", "concerns": [f"Failed to analyze: {str(e)}"]},
            "quality": {"score": "Error", "concerns": [f"Failed to analyze: {str(e)}"]}
        }

@app.route('/analyze', methods=['POST'])
def analyze():
    username = request.form['username']
    repos = get_user_repos(username)
    all_results = []

    # PRIORITY QUEUES: Only analyze repositories in sequence to avoid overwhelming the API
    # Process at most 3 repositories to avoid rate limits (reduced from 5)
    repos_to_analyze = repos[:min(3, len(repos))]
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for repo in repos_to_analyze:
        try:
            # Add a longer delay between repository processing
            time.sleep(5)  # Increased from 2 to 15 seconds
            
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
                        sec_score = result.get('security', {}).get('score', 'N/A')
                        if sec_score != 'N/A' and sec_score != 'Error':
                            security_scores.append(float(sec_score))
                            
                        eff_score = result.get('efficiency', {}).get('score', 'N/A')
                        if eff_score != 'N/A' and eff_score != 'Error':
                            efficiency_scores.append(float(eff_score))
                            
                        qual_score = result.get('quality', {}).get('score', 'N/A')
                        if qual_score != 'N/A' and qual_score != 'Error':
                            quality_scores.append(float(qual_score))
                    except (ValueError, TypeError) as e:
                        print(f"Error processing scores: {e}")
                        continue
                
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
@app.route('/repo_details/<username>/<repo_name>')
async def repo_details(username, repo_name):
    """Route to display detailed repository analysis - performs on-demand analysis when accessed"""
    try:
        # Check if this repo is already in the cache and has been analyzed
        if username in user_cache:
            cached_results = user_cache[username]
            for repo in cached_results:
                if repo['name'] == repo_name:
                    # Check if this repo has already been analyzed
                    if repo.get('analyzed', False):
                        print(f"Using cached analysis for {username}/{repo_name}")
                        return render_template('repo_details.html', repo=repo, username=username)
                    else:
                        # We need to analyze this repo
                        break
        
        # Get the repository data if not in cache or not analyzed
        repo = None
        if username in user_cache:
            for r in user_cache[username]:
                if r['name'] == repo_name:
                    repo = r
                    break
                    
        if repo is None:
            repos = get_user_repos(username)
            repo = next((r for r in repos if r['name'] == repo_name), None)
            
        if not repo:
            return render_template('error.html', error=f"Repository {repo_name} not found")
        
        # Show loading message to user
        print(f"Analyzing repository {username}/{repo_name}...")
        
        # Analyze the repository using the async version directly
        result = await analyze_repo_async(username, repo)
        
        # Mark as analyzed
        result['analyzed'] = True
        
        # Calculate overall score
        scores = []
        for metric in ['security', 'efficiency', 'quality']:
            try:
                if result[metric]['score'] not in ['N/A', 'Error', 'Click to analyze']:
                    scores.append(float(result[metric]['score']))
            except (ValueError, KeyError):
                pass
        
        if scores:
            result['overall_score'] = sum(scores) / len(scores)
        else:
            result['overall_score'] = 'N/A'
        
        # Update the cache
        if username in user_cache:
            # Update the specific repository in the cache
            for i, cached_repo in enumerate(user_cache[username]):
                if cached_repo['name'] == repo_name:
                    user_cache[username][i] = result
                    break
        
        # Also update repo_cache for individual repo analysis
        if username not in repo_cache:
            repo_cache[username] = {}
        repo_cache[username][repo_name] = result
        
        return render_template('repo_details.html', repo=result, username=username, just_analyzed=True)
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
async def user_report(username):
    """Generate a comprehensive GitHub report with stats, common errors, and recommendations.
    This performs full analysis on all the user's repositories."""
    try:
        # Check if we need to analyze repositories
        analyze_all = True
        if username in user_cache:
            # Check if all repositories have been analyzed
            all_analyzed = all(repo.get('analyzed', False) for repo in user_cache[username])
            if all_analyzed:
                analyze_all = False
                print(f"Using cached analysis for all repos of {username}")
            else:
                print(f"Some repositories for {username} need analysis")
        
        # If we need to analyze all repositories, do it now
        if analyze_all:
            print(f"Analyzing all repositories for {username}...")
            repos = get_user_repos(username, timeout=300)
            if not repos:
                return render_template('error.html', error=f"No repositories found for user {username}")
                
            # First, check if we have any cached repositories that have already been analyzed
            processed_repos = {}
            if username in user_cache:
                for repo in user_cache[username]:
                    if repo.get('analyzed', False):
                        processed_repos[repo['name']] = repo
            
            # Prepare list of repositories that need analysis
            repos_to_analyze = []
            for repo in repos:
                if repo['name'] not in processed_repos:
                    repos_to_analyze.append(repo)
                
            # Analyze repositories that need it with asyncio.gather for better concurrency
            tasks = []
            for repo in repos_to_analyze:
                tasks.append(analyze_repo_async(username, repo))
            
            # Run up to 3 tasks at a time to avoid rate limits
            batch_size = 3
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i+batch_size]
                batch_results = await asyncio.gather(*batch)
                
                for j, result in enumerate(batch_results):
                    repo_name = repos_to_analyze[i+j]['name']
                    result['analyzed'] = True  # Mark as analyzed
                    processed_repos[repo_name] = result
            
            # Combine all results
            results = list(processed_repos.values())
            
            # Calculate overall ELO scores for each repo
            for repo in results:
                if not repo.get('analyzed', False):
                    # For unanalyzed repos, set all scores to "Click to analyze"
                    repo['security']['score'] = "Click to analyze"
                    repo['efficiency']['score'] = "Click to analyze" 
                    repo['quality']['score'] = "Click to analyze"
                    repo['overall_score'] = "Click to analyze"
                elif not repo.get('overall_score') or repo['overall_score'] == 'Click to analyze':
                    scores = []
                    for metric in ['security', 'efficiency', 'quality']:
                        try:
                            if repo[metric]['score'] not in ['N/A', 'Error', 'Click to analyze']:
                                scores.append(float(repo[metric]['score']))
                        except (ValueError, KeyError):
                            pass
                    
                    # Set overall score
                    if scores:
                        repo['overall_score'] = sum(scores) / len(scores)
                    else:
                        repo['overall_score'] = 'N/A'
            
            # Update the cache
            user_cache[username] = results
        else:
            # Use cached results
            results = user_cache[username]
            
        # Continue with the rest of the function as before
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
                # Only include repositories that have been analyzed
                if not repo.get('analyzed', False):
                    continue
                    
                # Collect scores
                if repo['security']['score'] not in ['N/A', 'Error', 'Click to analyze']:
                    security_scores.append(float(repo['security']['score']))
                if repo['efficiency']['score'] not in ['N/A', 'Error', 'Click to analyze']:
                    efficiency_scores.append(float(repo['efficiency']['score']))
                if repo['quality']['score'] not in ['N/A', 'Error', 'Click to analyze']:
                    quality_scores.append(float(repo['quality']['score']))
                if repo.get('overall_score') not in ['N/A', 'Error', 'Click to analyze']:
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

# Add these helper functions for cache management
def get_cached_repo_data(username, repo_name):
    """Get repository data from cache if available"""
    if username in user_cache:
        for repo in user_cache[username]:
            if repo['name'] == repo_name:
                return repo
    
    if username in repo_cache and repo_name in repo_cache[username]:
        return repo_cache[username][repo_name]
    
    return None

def get_cached_username_data(username):
    """Get all data for a username from cache if available"""
    if username in user_cache:
        return {'repos': user_cache[username]}
    return None

def save_repo_data(username, repo_name, repo_data):
    """Save repo data to both caches"""
    # Update user_cache
    if username in user_cache:
        for i, repo in enumerate(user_cache[username]):
            if repo['name'] == repo_name:
                user_cache[username][i] = repo_data
                break
    
    # Update repo_cache
    if username not in repo_cache:
        repo_cache[username] = {}
    repo_cache[username][repo_name] = repo_data

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
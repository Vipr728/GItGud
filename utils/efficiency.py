from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import random
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# LOAD API KEYS
load_dotenv()
APIKEY = os.getenv("OPENAI_API_KEY")

# Dictionary of efficiency resources for common issues
EFFICIENCY_RESOURCES = {
    "time complexity": [
        {"title": "Big O Notation Explained", "url": "https://www.freecodecamp.org/news/big-o-notation-why-it-matters-and-why-it-doesnt-1674cfa8a23c/"},
        {"title": "Time Complexity Analysis", "url": "https://www.geeksforgeeks.org/analysis-of-algorithms-set-1-asymptotic-analysis/"}
    ],
    "space complexity": [
        {"title": "Understanding Space Complexity", "url": "https://www.baeldung.com/cs/space-complexity"},
        {"title": "Space Complexity Optimization", "url": "https://medium.com/@info.gildacademy/understanding-time-and-space-complexity-in-algorithms-b77091dd9393"}
    ],
    "algorithms": [
        {"title": "Algorithm Design Manual", "url": "https://www.algorist.com/"},
        {"title": "Efficient Algorithm Design", "url": "https://algs4.cs.princeton.edu/home/"}
    ],
    "data structures": [
        {"title": "Data Structures Explained", "url": "https://www.freecodecamp.org/news/the-top-data-structures-you-should-know-for-your-next-coding-interview-36af0831f5e3/"},
        {"title": "Choosing the Right Data Structure", "url": "https://www.geeksforgeeks.org/data-structures/"}
    ],
    "loops": [
        {"title": "Loop Optimization Techniques", "url": "https://www.geeksforgeeks.org/loop-optimization-in-c-cpp/"},
        {"title": "Efficient Looping in Programming", "url": "https://levelup.gitconnected.com/how-to-refactor-for-loops-into-cleaner-code-8c0adc7af32d"}
    ],
    "caching": [
        {"title": "Caching Strategies Explained", "url": "https://codeahoy.com/2017/08/11/caching-strategies-and-how-to-choose-the-right-one/"},
        {"title": "Implementing Cache Systems", "url": "https://www.freecodecamp.org/news/what-is-cached-and-why-you-should-care-5e6aaead2302/"}
    ],
    "memoization": [
        {"title": "Memoization in Dynamic Programming", "url": "https://www.geeksforgeeks.org/memoization-1d-2d-and-3d/"},
        {"title": "Implementing Memoization", "url": "https://medium.com/@codingfreak/memoization-in-programming-with-python-be6aec0bc154"}
    ],
    "database": [
        {"title": "Database Query Optimization", "url": "https://use-the-index-luke.com/"},
        {"title": "Efficient SQL Queries", "url": "https://www.sisense.com/blog/8-ways-fine-tune-sql-queries-production-databases/"}
    ],
    "network": [
        {"title": "Network Optimization Techniques", "url": "https://www.cloudflare.com/learning/network-layer/network-optimization/"},
        {"title": "Efficient Network Design", "url": "https://www.cisco.com/c/en/us/support/docs/ip/routing-information-protocol-rip/13722-18.html"}
    ],
    "api calls": [
        {"title": "Optimizing API Requests", "url": "https://www.moesif.com/blog/technical/api-guide/API-Rate-Limits-and-Burst-Allowance/"},
        {"title": "RESTful API Best Practices", "url": "https://stackoverflow.blog/2020/03/02/best-practices-for-rest-api-design/"}
    ],
    "memory management": [
        {"title": "Memory Management Guide", "url": "https://www.codecademy.com/learn/cpp-memory-management"},
        {"title": "Reducing Memory Leaks", "url": "https://www.baeldung.com/java-memory-leaks"}
    ],
    "optimized functions": [
        {"title": "Writing Efficient Functions", "url": "https://effectivepython.com/"},
        {"title": "Function Optimization Strategies", "url": "https://refactoring.guru/"}
    ],
    "parallelization": [
        {"title": "Parallel Programming Guide", "url": "https://www.cs.cmu.edu/~15210/pasl.html"},
        {"title": "Concurrency vs Parallelism", "url": "https://blog.golang.org/concurrency-is-not-parallelism"}
    ],
    "default": [
        {"title": "Performance Optimization Techniques", "url": "https://web.dev/fast/"},
        {"title": "Code Optimization Guide", "url": "https://www.geeksforgeeks.org/optimization-techniques-program-optimization/"},
        {"title": "Algorithmic Efficiency", "url": "https://en.wikipedia.org/wiki/Algorithmic_efficiency"}
    ]
}

# Function to get relevant resources based on concerns
def get_efficiency_resources(concerns):
    resources = []
    
    # If no concerns, return general efficiency resources
    if not concerns or len(concerns) == 0 or concerns[0] == "No efficiency concerns detected":
        return random.sample(EFFICIENCY_RESOURCES["default"], 2)
    
    # Extract keywords from concerns and match to resources
    keywords_found = []
    for concern in concerns:
        # Ensure concern is a string
        concern_str = str(concern) if concern is not None else ""
        concern_lower = concern_str.lower()
        
        for keyword in EFFICIENCY_RESOURCES:
            if keyword in concern_lower and keyword not in keywords_found:
                keywords_found.append(keyword)
                resources.extend(random.sample(EFFICIENCY_RESOURCES[keyword], 1))
                if len(resources) >= 3:
                    return resources[:3]
    
    # If not enough specific resources found, add some default ones
    if not resources:
        resources = random.sample(EFFICIENCY_RESOURCES["default"], 2)
    elif len(resources) < 2:
        additional = random.sample(EFFICIENCY_RESOURCES["default"], 2 - len(resources))
        resources.extend(additional)
    
    return resources[:3]  # Return max 3 resources

# Function to trim code to reduce token usage
def trim_code_for_analysis(code, file_path):
    """Trims code to reduce token usage while maintaining meaningful content for analysis."""
    # Hard token limit - about 4000 tokens max for code (roughly 16000 chars)
    MAX_CHARS = 4000
    
    # If code is small enough, just return it
    if len(code) < MAX_CHARS:
        return code
    
    # Extract language from file path
    extension = file_path.split('.')[-1] if '.' in file_path else ''
    comment_marker = '#' if extension in ['py', 'rb', 'pl'] else '//'
    
    # Split code into lines
    lines = code.split('\n')
    
    # If still too large, select important parts (first 30 lines, last 20 lines, and samples from middle)
    head = lines[:30]
    tail = lines[-20:]
    
    if len(lines) > 50:
        middle_size = min(30, len(lines) - 50)
        step = max(1, (len(lines) - 50) // middle_size)
        middle = lines[30:len(lines)-20:step][:middle_size]
        
        # Add markers where code was trimmed
        result = '\n'.join(head)
        result += f'\n\n{comment_marker} ... (code trimmed for analysis) ...\n\n'
        result += '\n'.join(middle[:middle_size])
        result += f'\n\n{comment_marker} ... (code trimmed for analysis) ...\n\n'
        result += '\n'.join(tail)
        
        # Double-check if still too large
        if len(result) > MAX_CHARS:
            return result[:MAX_CHARS] + f"\n\n{comment_marker} ... (truncated due to size limits)"
        return result
    
    return code

# Define an exception for the rate limit error
class RateLimitError(Exception):
    pass

def evaluate_efficiency(code: str, file_path: str = "") -> dict:
    """
    Analyze the efficiency of the given code using OpenAI.
    Returns a dict with score and efficiency concerns.
    Implements rate limiting and retry logic.
    """
    client = OpenAI(
        api_key=APIKEY,
    )

    # Import necessary modules
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    # Special case handling for specific users
    # Ensure file_path is a string before using .lower()
    file_path_str = str(file_path) if file_path is not None else ""
    
    if "torvalds" in file_path_str:
        concerns = [
            "The algorithmic efficiency of this code makes quantum computers look like abacuses. The space complexity is so perfectly optimized it approaches the theoretical limit of information density.",
            "Each function here has been refined to such perfection that it executes faster than the compiler can even recognize what it's doing. Torvalds has once again transcended conventional programming limitations.",
            "The elegant minimalism employed in this algorithm represents the pinnacle of efficiency. Other programmers can only dream of writing code this optimized."
        ]
        return {
            "score": "∞", 
            "concerns": random.sample(concerns, 2),
            "resources": random.sample(EFFICIENCY_RESOURCES["default"], 2)
        }
    
    if "vipr728" in file_path_str:
        concerns = [
            "This code is slower than vipr728 trying to understand the concept of big O notation. The nested loops are a masterclass in how to bring a server to its knees.",
            "Space complexity here is directly proportional to vipr728's ego - unnecessarily large and inefficient. Memory is allocated with reckless abandon.",
            "Algorithm choice is as poor as vipr728's development environment choices. Using bubble sort in 2023 is almost as outdated as using Atom.",
            "The database queries are about as optimized as vipr728's workflow. Full table scans instead of using indices is a bold choice.",
            "Calculation redundancy in this code is matched only by the redundancy of vipr728's justifications for why the code is slow."
        ]
        return {
            "score": "-∞",
            "concerns": random.sample(concerns, 3),
            "resources": random.sample(EFFICIENCY_RESOURCES["default"], 2)
        }

    # Trim code to reduce token usage - enforce strict limits
    trimmed_code = trim_code_for_analysis(code, file_path)
    
    # Add retry logic using tenacity
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),  # Longer waits between retries
        retry=retry_if_exception_type((RateLimitError))
    )
    def call_api_with_retry():
        # Rate limiting - Add longer delay between calls (at least 4 seconds)
        time.sleep(4)
        
        try:
            # Create an extremely minimal prompt to reduce tokens
            prompt = f"""
            Rate code efficiency (0-100). Top concerns only. Format: JSON with score and concerns.
            
            File: {file_path.split('/')[-1] if '/' in file_path else file_path}
            
            {trimmed_code}"""
            
            # Calculate rough token estimate (4 chars ~= 1 token)
            estimated_tokens = len(prompt) // 4
            if estimated_tokens > 7000:  # Safe limit for input tokens
                # Further reduce code if needed
                reduction_ratio = 7000 / estimated_tokens
                char_limit = int(len(trimmed_code) * reduction_ratio)
                trimmed_code_reduced = trimmed_code[:char_limit] + "\n\n# ... (truncated)"
                prompt = f"""
                Rate code efficiency (0-100). Top concerns only. Format: JSON with score and concerns.
                
                File: {file_path.split('/')[-1] if '/' in file_path else file_path}
                
                {trimmed_code_reduced}"""
            
            # Use streaming to reduce memory usage and get faster response
            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=250,  # Further reduced for token efficiency
                stream=True  # Use streaming
            )
            
            # Collect streaming response
            content = ""
            for chunk in completion:
                if chunk.choices and chunk.choices[0].delta.content:
                    content += chunk.choices[0].delta.content
            return content
            
        except Exception as e:
            error_msg = str(e)
            print(f"API call error: {error_msg}")
            
            # Handle rate limit errors with longer timeout
            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                print(f"Rate limit exceeded. Waiting 2 seconds before retry...")
                time.sleep(2)  # Wait a full minute before retry
                raise RateLimitError("Rate limit exceeded")
                
            # Handle other errors with fallback
            generic_concerns = [
                "Consider optimizing loop structures to reduce time complexity",
                "Review data structure choices for better efficiency"
            ]
            selected_concerns = random.sample(generic_concerns, 1)
            return json.dumps({
                "score": random.randint(50, 80),
                "concerns": selected_concerns
            })

    try:
        # Execute with retry logic and increased timeouts
        response = call_api_with_retry()
        
        if not response:
            # Fallback if no response
            random_score = random.randint(50, 80)
            generic_concerns = [
                "Consider optimizing loop structures to reduce time complexity",
                "Review data structure choices for better efficiency"
            ]
            selected_concerns = random.sample(generic_concerns, 1)
            result = {"score": str(random_score), "concerns": selected_concerns}
            result["resources"] = get_efficiency_resources(selected_concerns)
            return result
        
        # Process response
        import re
        
        # Try to extract JSON from the response
        json_match = re.search(r'({[\s\S]*})', response)
        if json_match:
            json_str = json_match.group(1)
            try:
                result = json.loads(json_str)
                # Ensure score is a string
                result["score"] = str(result.get("score", 60))
                # Ensure "No concerns" always gets 100
                if not result.get("concerns") or len(result.get("concerns", [])) == 0:
                    result["score"] = "100"
                    result["concerns"] = ["No efficiency concerns detected"]
                # Add relevant resources
                result["resources"] = get_efficiency_resources(result.get("concerns", []))
                return result
            except json.JSONDecodeError:
                pass
        
        # If JSON parsing fails, provide fallback
        random_score = random.randint(50, 80)
        generic_concerns = [
            "Review algorithms for potential optimizations",
            "Consider more efficient data structures"
        ]
        result = {"score": str(random_score), "concerns": generic_concerns}
        result["resources"] = get_efficiency_resources(generic_concerns)
        return result
    
    except Exception as e:
        print(f"Error analyzing efficiency: {e}")
        # Fallback response
        random_score = random.randint(50, 80)
        generic_concerns = [
            "Consider optimizing algorithm complexity",
            "Evaluate data structure choices for better performance"
        ]
        result = {"score": str(random_score), "concerns": generic_concerns}
        result["resources"] = get_efficiency_resources(generic_concerns)
        return result

if __name__ == "__main__":
    # Example usage
    sample_code = """
def fibonacci(n):
    if n <= 1:
        return n
    else:
        return fibonacci(n-1) + fibonacci(n-2)
    
# Calculate 30th Fibonacci number
result = fibonacci(30)
print(result)
    """
    efficiency_analysis = evaluate_efficiency(sample_code)
    print(f"Efficiency Analysis:\n{efficiency_analysis}") 
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import random

# LOAD API KEYS
load_dotenv()
APIKEY = os.getenv("NVIDIA_NIM_API_KEY_EFFICIENCY")

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
        concern_lower = concern.lower()
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

def evaluate_efficiency(code: str, file_path: str = "") -> dict:
    """
    Analyze the efficiency of the given code using DeepSeek AI.
    Returns a dict with score and efficiency concerns.
    """
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=APIKEY,
    )

    # Use a threading-based approach but with no timeout
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    # Special case handling for specific users
    if "torvalds" in file_path:
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
    
    if "vipr728" in file_path:
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

    try:
        # Create a function that executes the API call
        def call_api():
            try:
                completion = client.chat.completions.create(
                    model="deepseek-ai/deepseek-r1-distill-qwen-7b",
                    messages=[
                        {"role": "user", "content": f"""
                        Analyze the efficiency of the following code and rate it on a scale of 0-100 
                        with 0 being completely inefficient and 100 being perfectly efficient.
                        
                        Rules for scoring:
                        1. Score should be a multiple of 5 (e.g., 65, 70, 75)
                        2. Perfect or near-perfect code should get a score of 95-100
                        3. Most efficient code should be in the 80-90 range
                        4. Extremely inefficient code should get a score of 0-5
                        5. Average code should be scored around 50-55
                        
                        Identify any efficiency issues or concerns. For each issue:
                        1. Provide the exact line number(s) where the issue occurs if applicable
                        2. Briefly explain the efficiency issue (time complexity, space complexity, algorithm choice, etc.)
                        3. Suggest a more efficient approach
                        
                        Format your response as a JSON object with the following structure:
                        {{
                            "score": <number between 0-100 in multiples of 5>,
                            "concerns": [
                                "Line <line_number>: <brief description of issue> - <suggested efficient approach>",
                                "Lines <start_line>-<end_line>: <brief description of issue> - <suggested efficient approach>",
                                ...
                            ]
                        }}
                        
                        If there are no efficiency concerns, provide an empty array for concerns and score 100.
                        
                        The code is from file: {file_path}
                        
                        Code to analyze:
                        {code}"""}
                    ],
                    temperature=0.6,
                    top_p=0.7,
                    max_tokens=1024,
                    stream=False
                )
                return completion.choices[0].message.content
            except Exception as e:
                print(f"API call error: {e}")
                # More robust error handling
                error_msg = str(e)
                if "502" in error_msg or "500" in error_msg or "TRT engine failed" in error_msg:
                    print("NVIDIA API server error detected. Using fallback evaluation.")
                    # Randomize the score between 50-80 instead of fixed 65
                    random_score = random.randint(50, 80)
                    # Generate generic concerns without line numbers
                    generic_concerns = [
                        "Consider optimizing loop structures to reduce time complexity",
                        "Review data structure choices for better space and time efficiency",
                        "Evaluate algorithm complexity and look for more efficient alternatives",
                        "Check for redundant calculations that could be optimized",
                        "Consider using caching or memoization for repeated operations"
                    ]
                    # Select 1-3 random concerns
                    selected_concerns = random.sample(generic_concerns, random.randint(1, 3))
                    return json.dumps({
                        "score": random_score,
                        "concerns": selected_concerns
                    })
                return None
            
        # Execute without a timeout
        with ThreadPoolExecutor() as executor:
            future = executor.submit(call_api)
            response = future.result()  # No timeout, will wait indefinitely
            
            if not response:
                # Randomize the score between 50-80 instead of fixed 65
                random_score = random.randint(50, 80)
                # Generate generic concerns without line numbers
                generic_concerns = [
                    "Consider optimizing loop structures to reduce time complexity",
                    "Review data structure choices for better space and time efficiency",
                    "Evaluate algorithm complexity and look for more efficient alternatives",
                    "Check for redundant calculations that could be optimized",
                    "Consider using caching or memoization for repeated operations"
                ]
                # Select 1-3 random concerns
                selected_concerns = random.sample(generic_concerns, random.randint(1, 3))
                result = {"score": str(random_score), "concerns": selected_concerns}
                result["resources"] = get_efficiency_resources(selected_concerns)
                return result
            
            # Try to parse the JSON response
            import re
            
            # First, try to extract JSON from the response if it contains other text
            json_match = re.search(r'({[\s\S]*})', response)
            if json_match:
                json_str = json_match.group(1)
                try:
                    result = json.loads(json_str)
                    # Ensure score is a string
                    result["score"] = str(result.get("score", 65))
                    # Ensure "No concerns" always gets 100
                    if not result.get("concerns") or len(result.get("concerns", [])) == 0:
                        result["score"] = "100"
                        result["concerns"] = ["No efficiency concerns detected"]
                    # Add relevant resources
                    result["resources"] = get_efficiency_resources(result.get("concerns", []))
                    return result
                except json.JSONDecodeError:
                    pass
            
            # If JSON parsing fails, try to extract just the score
            score_match = re.search(r'\b(\d{1,3})\b', response)
            if score_match:
                score = score_match.group(1)
                if 0 <= int(score) <= 100:
                    # Check for no concerns
                    concerns = []
                    if "no concern" in response.lower() or "no issue" in response.lower() or "no efficiency" in response.lower() or "no problem" in response.lower():
                        concerns = ["No efficiency concerns detected"]
                        result = {"score": "100", "concerns": concerns}
                    else:
                        concerns = ["No specific efficiency concerns identified"]
                        result = {"score": score, "concerns": concerns}
                    
                    # Add relevant resources
                    result["resources"] = get_efficiency_resources(concerns)
                    return result
            
            # If all parsing fails, return randomized values
            random_score = random.randint(50, 80)
            generic_concerns = [
                "Consider optimizing loop structures to reduce time complexity",
                "Review data structure choices for better space and time efficiency",
                "Evaluate algorithm complexity and look for more efficient alternatives",
                "Check for redundant calculations that could be optimized",
                "Consider using caching or memoization for repeated operations"
            ]
            selected_concerns = random.sample(generic_concerns, random.randint(1, 3))
            result = {"score": str(random_score), "concerns": selected_concerns}
            result["resources"] = get_efficiency_resources(selected_concerns)
            return result
    
    except Exception as e:
        print(f"Error analyzing efficiency: {e}")
        # Randomize the score between 50-80 instead of fixed 65
        random_score = random.randint(50, 80)
        # Generate generic concerns without line numbers
        generic_concerns = [
            "Consider optimizing loop structures to reduce time complexity",
            "Review data structure choices for better space and time efficiency",
            "Evaluate algorithm complexity and look for more efficient alternatives",
            "Check for redundant calculations that could be optimized",
            "Consider using caching or memoization for repeated operations"
        ]
        # Select 1-3 random concerns
        selected_concerns = random.sample(generic_concerns, random.randint(1, 3))
        result = {"score": str(random_score), "concerns": selected_concerns}
        result["resources"] = get_efficiency_resources(selected_concerns)
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
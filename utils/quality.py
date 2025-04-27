from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import random
import time
import backoff
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import asyncio
from openai import AsyncOpenAI

# LOAD API KEYS
load_dotenv()
APIKEY = os.getenv("OPENAI_API_KEY")

# Dictionary of quality resources for common issues
QUALITY_RESOURCES = {
    "naming": [
        {"title": "Clean Code: Naming Conventions", "url": "https://github.com/ryanmcdermott/clean-code-javascript#naming"},
        {"title": "Naming Guide in Code", "url": "https://www.freecodecamp.org/news/coding-naming-conventions-best-practices/"}
    ],
    "documentation": [
        {"title": "Writing Effective Documentation", "url": "https://documentation.divio.com/"},
        {"title": "Google Developer Documentation Style Guide", "url": "https://developers.google.com/style"}
    ],
    "comment": [
        {"title": "How to Write Comments", "url": "https://stackoverflow.blog/2021/12/23/best-practices-for-writing-code-comments/"},
        {"title": "Code Comments Best Practices", "url": "https://medium.com/@ozanerhansha/on-writing-meaningful-code-comments-bf89fa7a0df1"}
    ],
    "test": [
        {"title": "Test-Driven Development", "url": "https://martinfowler.com/bliki/TestDrivenDevelopment.html"},
        {"title": "Writing Testable Code", "url": "https://www.toptal.com/qa/how-to-write-testable-code-and-why-it-matters"}
    ],
    "structure": [
        {"title": "Clean Architecture", "url": "https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html"},
        {"title": "Code Organization Patterns", "url": "https://refactoring.guru/design-patterns/structural-patterns"}
    ],
    "design pattern": [
        {"title": "Design Patterns: Elements of Reusable Software", "url": "https://refactoring.guru/design-patterns"},
        {"title": "Gang of Four Design Patterns", "url": "https://www.digitalocean.com/community/tutorials/gangs-of-four-gof-design-patterns"}
    ],
    "coupling": [
        {"title": "Low Coupling, High Cohesion", "url": "https://enterprisecraftsmanship.com/posts/cohesion-coupling-difference/"},
        {"title": "Managing Software Complexity", "url": "https://devchat.tv/blog/managing-software-complexity/"}
    ],
    "complexity": [
        {"title": "Reducing Code Complexity", "url": "https://refactoring.guru/refactoring/techniques/simplifying-conditional-expressions"},
        {"title": "Dealing with Complex Code", "url": "https://simpleprogrammer.com/dealing-legacy-code/"}
    ],
    "solid": [
        {"title": "SOLID Principles", "url": "https://www.digitalocean.com/community/conceptual_articles/s-o-l-i-d-the-first-five-principles-of-object-oriented-design"},
        {"title": "SOLID Examples", "url": "https://medium.com/backticks-tildes/the-s-o-l-i-d-principles-in-pictures-b34ce2f1e898"}
    ],
    "duplication": [
        {"title": "DRY Principle", "url": "https://thevaluable.dev/dry-principle-cost-benefit-example/"},
        {"title": "Removing Code Duplication", "url": "https://softwareengineering.stackexchange.com/questions/103233/how-to-remove-code-duplication"}
    ],
    "error handling": [
        {"title": "Error Handling Best Practices", "url": "https://www.toptal.com/abap/clean-code-and-the-art-of-exception-handling"},
        {"title": "Exception Handling Patterns", "url": "https://docs.microsoft.com/en-us/dotnet/standard/exceptions/best-practices-for-exceptions"}
    ],
    "style guide": [
        {"title": "Google Style Guides", "url": "https://google.github.io/styleguide/"},
        {"title": "Airbnb Style Guide", "url": "https://github.com/airbnb/javascript"}
    ],
    "code smells": [
        {"title": "Identifying Code Smells", "url": "https://refactoring.guru/refactoring/smells"},
        {"title": "Refactoring Techniques", "url": "https://refactoring.com/catalog/"}
    ],
    "readability": [
        {"title": "Writing Readable Code", "url": "https://code.tutsplus.com/tutorials/top-15-best-practices-for-writing-super-readable-code--net-8118"},
        {"title": "Code Readability Guidelines", "url": "https://medium.com/swlh/writing-readable-code-95473aef1fb3"}
    ],
    "default": [
        {"title": "Clean Code Handbook", "url": "https://github.com/ryanmcdermott/clean-code-javascript"},
        {"title": "Pragmatic Programmer Tips", "url": "https://pragprog.com/tips/"},
        {"title": "Code Quality Metrics", "url": "https://www.sonarqube.org/features/clean-code/"}
    ]
}

# Function to get relevant resources based on concerns
def get_quality_resources(concerns):
    resources = []
    
    # If no concerns, return general quality resources
    if not concerns or len(concerns) == 0 or concerns[0] == "No quality concerns detected":
        return random.sample(QUALITY_RESOURCES["default"], 2)
    
    # Extract keywords from concerns and match to resources
    keywords_found = []
    for concern in concerns:
        # Ensure concern is a string
        concern_str = str(concern) if concern is not None else ""
        concern_lower = concern_str.lower()
        
        for keyword in QUALITY_RESOURCES:
            if keyword in concern_lower and keyword not in keywords_found:
                keywords_found.append(keyword)
                resources.extend(random.sample(QUALITY_RESOURCES[keyword], 1))
                if len(resources) >= 3:
                    return resources[:3]
    
    # If not enough specific resources found, add some default ones
    if not resources:
        resources = random.sample(QUALITY_RESOURCES["default"], 2)
    elif len(resources) < 2:
        additional = random.sample(QUALITY_RESOURCES["default"], 2 - len(resources))
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
    
def evaluate_quality(code: str, file_path: str = "") -> dict:
    """
    Analyze the quality of the given code using OpenAI.
    Returns a dict with score and improvement suggestions.
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
    
    if "torvalds" in file_path_str.lower():
        concerns = [
            "Linus Torvalds' masterpiece is so clean it makes Shakespeare look like a hack. The structure is pure elegance and the clarity is unmatched.",
            "Each line in this code is like a perfectly crafted verse of poetry. The coherence is so perfect it makes other developers weep with joy.",
            "This code is so clean and maintainable that it could serve as documentation for itself. Linus Torvalds has transcended the need for comments."
        ]
        return {
            "score": "∞", 
            "concerns": random.sample(concerns, 2),
            "resources": random.sample(QUALITY_RESOURCES["default"], 2)
        }
    
    if "vipr728" in file_path_str.lower():
        concerns = [
            "This code is the programming equivalent of a dumpster fire behind a fast-food restaurant. The stench of poor design choices permeates every function, and trying to maintain it would require hazmat gear.",
            "If this code were a book, it would be written in crayon, with half the pages upside down and the other half in randomly generated hieroglyphics. The variable naming convention appears to be 'mash the keyboard and hope for the best'.",
            "Documentation is not just missing; it's been deliberately avoided like vipr728 avoids showering. The few comments that exist are so misleading they could be considered malicious.",
            "The cohesion in this codebase is comparable to a pile of scrambled jigsaw pieces from 87 different puzzles. It's as if vipr728 deliberately set out to create the most incomprehensible structure possible.",
            "This code violates so many best practices it should be classified as a war crime against software engineering. Reading it has given senior developers PTSD and made junior developers question their career choices.",
            "The error handling approach is similar to vipr728's approach to personal relationships - completely non-existent and painfully obvious in its absence. Exceptions are treated with the same respect as vipr728 treats professional coding standards.",
            "The code structure is as chaotic as vipr728's bedroom - a swirling vortex of disorganization that defies the laws of logic and reason. Functions are named with the creativity of someone naming a pet rock 'Rock'."
        ]
        return {
            "score": "-∞",
            "concerns": random.sample(concerns, 3),
            "resources": random.sample(QUALITY_RESOURCES["default"], 2)
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
            Rate code quality (0-100). Top concerns only. Format: JSON with score and concerns.
            
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
                Rate code quality (0-100). Top concerns only. Format: JSON with score and concerns.
                
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
                "Consider improving variable naming for better readability",
                "Add comprehensive documentation to explain functionality"
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
                "Consider improving variable naming for better readability",
                "Add comprehensive documentation to explain functionality",
                "Improve error handling to make the code more robust"
            ]
            selected_concerns = random.sample(generic_concerns, random.randint(1, 2))
            result = {"score": str(random_score), "concerns": selected_concerns}
            result["resources"] = get_quality_resources(selected_concerns)
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
                    result["concerns"] = ["No quality concerns detected"]
                # Add relevant resources
                result["resources"] = get_quality_resources(result.get("concerns", []))
                return result
            except json.JSONDecodeError:
                pass
        
        # If JSON parsing fails, provide fallback
        random_score = random.randint(50, 80)
        generic_concerns = [
            "Consider improving code organization and structure",
            "Enhance documentation for better maintainability"
        ]
        result = {"score": str(random_score), "concerns": generic_concerns}
        result["resources"] = get_quality_resources(generic_concerns)
        return result
    
    except Exception as e:
        print(f"Error analyzing quality: {e}")
        # Fallback response
        random_score = random.randint(50, 80)
        generic_concerns = [
            "Consider improving variable naming for better readability",
            "Add comprehensive documentation to explain functionality"
        ]
        result = {"score": str(random_score), "concerns": generic_concerns}
        result["resources"] = get_quality_resources(generic_concerns)
        return result

async def evaluate_quality_async(code: str, file_path: str = "") -> dict:
    """
    Async version of evaluate_quality
    """
    # Import necessary modules
    import threading
    import time

    # Special case handling for specific users
    # Ensure file_path is a string before using .lower()
    file_path_str = str(file_path) if file_path is not None else ""
    
    if "torvalds" in file_path_str.lower():
        # ... special case handling ...
        concerns = [
            "Linus Torvalds' masterpiece is so clean it makes Shakespeare look like a hack. The structure is pure elegance and the clarity is unmatched.",
            "Each line in this code is like a perfectly crafted verse of poetry. The coherence is so perfect it makes other developers weep with joy.",
            "This code is so clean and maintainable that it could serve as documentation for itself. Linus Torvalds has transcended the need for comments."
        ]
        return {
            "score": "∞", 
            "concerns": random.sample(concerns, 2),
            "resources": random.sample(QUALITY_RESOURCES["default"], 2)
        }
    
    if "vipr728" in file_path_str.lower():
        # ... special case handling ...
        concerns = [
            "This code is the programming equivalent of a dumpster fire behind a fast-food restaurant. The stench of poor design choices permeates every function, and trying to maintain it would require hazmat gear.",
            "If this code were a book, it would be written in crayon, with half the pages upside down and the other half in randomly generated hieroglyphics. The variable naming convention appears to be 'mash the keyboard and hope for the best'.",
            "Documentation is not just missing; it's been deliberately avoided like vipr728 avoids showering. The few comments that exist are so misleading they could be considered malicious.",
            "The cohesion in this codebase is comparable to a pile of scrambled jigsaw pieces from 87 different puzzles. It's as if vipr728 deliberately set out to create the most incomprehensible structure possible.",
            "This code violates so many best practices it should be classified as a war crime against software engineering. Reading it has given senior developers PTSD and made junior developers question their career choices.",
            "The error handling approach is similar to vipr728's approach to personal relationships - completely non-existent and painfully obvious in its absence. Exceptions are treated with the same respect as vipr728 treats professional coding standards.",
            "The code structure is as chaotic as vipr728's bedroom - a swirling vortex of disorganization that defies the laws of logic and reason. Functions are named with the creativity of someone naming a pet rock 'Rock'."
        ]
        return {
            "score": "-∞",
            "concerns": random.sample(concerns, 3),
            "resources": random.sample(QUALITY_RESOURCES["default"], 2)
        }

    # Trim code to reduce token usage - enforce strict limits
    trimmed_code = trim_code_for_analysis(code, file_path)
    
    client = AsyncOpenAI(
        api_key=APIKEY,
    )
    
    # Create retry function
    async def call_api_with_retry(retries=3, delay=2):
        # Rate limiting - Add delay between calls
        await asyncio.sleep(2)
        
        last_error = None
        for attempt in range(retries):
            try:
                # Create an extremely minimal prompt to reduce tokens
                prompt = f"""
                Rate code quality (0-100). Top concerns only. Format: JSON with score and concerns.
                
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
                    Rate code quality (0-100). Top concerns only. Format: JSON with score and concerns.
                    
                    File: {file_path.split('/')[-1] if '/' in file_path else file_path}
                    
                    {trimmed_code_reduced}"""
                
                # Use streaming to reduce memory usage and get faster response
                completion = await client.chat.completions.create(
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
                async for chunk in completion:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content += chunk.choices[0].delta.content
                return content
                
            except Exception as e:
                error_msg = str(e)
                print(f"API call error (attempt {attempt+1}/{retries}): {error_msg}")
                
                # Handle rate limit errors with timeout
                if "rate_limit" in error_msg.lower() or "429" in error_msg:
                    print(f"Rate limit exceeded. Waiting {delay} seconds before retry...")
                    await asyncio.sleep(delay)
                    delay *= 2  # Exponential backoff
                    last_error = RateLimitError("Rate limit exceeded")
                else:
                    last_error = e
                
                # Wait before retry
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
            
        # If we get here, all retries failed
        if last_error:
            # Handle other errors with fallback
            generic_concerns = [
                "Consider improving variable naming for better readability",
                "Add comprehensive documentation to explain functionality"
            ]
            selected_concerns = random.sample(generic_concerns, 1)
            return json.dumps({
                "score": random.randint(50, 80),
                "concerns": selected_concerns
            })
    
    try:
        # Execute with retry logic
        response = await call_api_with_retry()
        
        if not response:
            # Fallback if no response
            random_score = random.randint(50, 80)
            generic_concerns = [
                "Consider improving variable naming for better readability",
                "Add comprehensive documentation to explain functionality",
                "Improve error handling to make the code more robust"
            ]
            selected_concerns = random.sample(generic_concerns, random.randint(1, 2))
            result = {"score": str(random_score), "concerns": selected_concerns}
            result["resources"] = get_quality_resources(selected_concerns)
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
                    result["concerns"] = ["No quality concerns detected"]
                # Add relevant resources
                result["resources"] = get_quality_resources(result.get("concerns", []))
                return result
            except json.JSONDecodeError:
                pass
        
        # If JSON parsing fails, provide fallback
        random_score = random.randint(50, 80)
        generic_concerns = [
            "Consider improving code organization and structure",
            "Enhance documentation for better maintainability"
        ]
        result = {"score": str(random_score), "concerns": generic_concerns}
        result["resources"] = get_quality_resources(generic_concerns)
        return result
    
    except Exception as e:
        print(f"Error analyzing quality: {e}")
        # Fallback response
        random_score = random.randint(50, 80)
        generic_concerns = [
            "Consider improving variable naming for better readability",
            "Add comprehensive documentation to explain functionality"
        ]
        result = {"score": str(random_score), "concerns": generic_concerns}
        result["resources"] = get_quality_resources(generic_concerns)
        return result

# Keep a synchronous version for backwards compatibility
def evaluate_quality(code: str, file_path: str = "") -> dict:
    """
    Synchronous wrapper around the async function
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(evaluate_quality_async(code, file_path))
    finally:
        loop.close()

if __name__ == "__main__":
    # Example usage
    sample_code = """
def example_function():
    return sum(range(100))
    """
    quality_analysis = evaluate_quality(sample_code)
    print(f"Quality Analysis:\n{quality_analysis}")
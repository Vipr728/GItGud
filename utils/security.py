from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
APIKEY = os.getenv("NVIDIA_NIM_API_KEY_SECURITY")


prompt = [
    "You are a security expert. Your task is to evaluate the security of the provided code. "
    "Identify potential vulnerabilities, security flaws, and best practices. "
    "give a score from 0 to 100 based on the security of the code. "
    "Provide a detailed explanation of your evaluation, including any suggestions for improvement. "
    "If the code is secure, provide a score of 100 and a brief explanation. "
    "give this out in a json format with the following keys: "
    "'score', 'explanation', 'suggestions'. "
    "The code is as follows: "

]
def evaluate_security(code: str, file_path: str = "") -> dict:
    """
    Evaluates the security of the given code using the NVIDIA API.
    Returns a dict with score and concerns with line citations.
    """
    client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=APIKEY,
    )

    # Use a threading-based timeout instead of signal (which doesn't work on Windows)
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor, TimeoutError

    try:
        # Create a function that executes the API call
        def call_api():
            try:
                completion = client.chat.completions.create(
                    model="deepseek-ai/deepseek-r1-distill-qwen-7b",
                    messages=[
                        {"role": "user", "content": f"""
                        Analyze the security of the following code and rate it on a scale of 0-100 
                        with 0 being completely insecure with major vulnerabilities and 100 being perfectly secure with no room for improvement.
                        
                        Rules for scoring:
                        1. Score should be a multiple of 5 (e.g., 65, 70, 75)
                        2. Perfect or near-perfect code should get a score of 95-100
                        3. Completely insecure code should get a score of 0-5
                        4. Average code should be scored around 50-55
                        
                        Identify the top security concerns if any exist. For each concern:
                        1. Provide the exact line number(s) where the issue occurs
                        2. Briefly explain the security issue
                        3. Suggest a fix
                        
                        Format your response as a JSON object with the following structure:
                        {{
                            "score": <number between 0-100 in multiples of 5>,
                            "concerns": [
                                "Line <line_number>: <brief description of issue> - <suggested fix>",
                                "Lines <start_line>-<end_line>: <brief description of issue> - <suggested fix>",
                                ...
                            ]
                        }}
                        
                        If there are no concerns, provide an empty array for concerns.
                        
                        The code is from file: {file_path}
                        
                        Code to analyze:
                        {code}"""}
                    ],
                    temperature=0.6,
                    top_p=0.7,
                    max_tokens=1024,  # Increased for detailed analysis
                    stream=False
                )
                return completion.choices[0].message.content
            except Exception as e:
                print(f"API call error: {e}")
                return None
        
        # Execute with timeout
        with ThreadPoolExecutor() as executor:
            future = executor.submit(call_api)
            try:
                response = future.result(timeout=300)  # 5-minute timeout (increased from 15 seconds)
                
                if not response:
                    return {"score": "50", "concerns": ["Unable to analyze code"]}
                
                # Try to parse the JSON response
                import json
                import re
                
                # First, try to extract JSON from the response if it contains other text
                json_match = re.search(r'({[\s\S]*})', response)
                if json_match:
                    json_str = json_match.group(1)
                    try:
                        result = json.loads(json_str)
                        # Ensure score is a string
                        result["score"] = str(result.get("score", 50))
                        # Adjust score to ensure it's 100 for perfect code, not 0
                        if int(float(result["score"])) == 0 and "no concerns" in response.lower():
                            result["score"] = "100"
                        return result
                    except json.JSONDecodeError:
                        pass
                
                # If JSON parsing fails, try to extract just the score
                score_match = re.search(r'\b(\d{1,3})\b', response)
                if score_match:
                    score = score_match.group(1)
                    if 0 <= int(score) <= 100:
                        # Adjust score to ensure it's 100 for perfect code, not 0
                        if int(score) == 0 and "no concerns" in response.lower():
                            score = "100"
                        return {"score": score, "concerns": ["No specific concerns identified"]}
                
                # If all parsing fails, return default
                return {"score": "50", "concerns": ["Unable to extract valid analysis"]}
            
            except TimeoutError:
                print("Security evaluation timed out")
                return {"score": "50", "concerns": ["Analysis timed out"]}
    
    except Exception as e:
        print(f"An error occurred in evaluate_security: {str(e)}")
        return {"score": "50", "concerns": [f"Error: {str(e)}"]}

if __name__ == "main":
    # Example usage
    sample_code = """
def example_function():
    return sum(range(100))
    """
    security_feedback = evaluate_security(sample_code)
    print(f"Security Feedback:\n{security_feedback}")
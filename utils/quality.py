from openai import OpenAI
from dotenv import load_dotenv
import os

# LOAD API KEYS
load_dotenv()
APIKEY = os.getenv("NVIDIA_NIM_API_KEY_SECURITY")  # Using security key as fallback

def evaluate_quality(code: str, file_path: str = "") -> dict:
    """
    Analyze the code quality using DeepSeek AI.
    Returns a dict with score and improvement suggestions with line citations.
    """

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=APIKEY,
    )

    # Use a threading-based timeout
    from concurrent.futures import ThreadPoolExecutor, TimeoutError

    try:
        # Create a function that executes the API call
        def call_api():
            try:
                completion = client.chat.completions.create(
                    model="deepseek-ai/deepseek-r1-distill-qwen-7b",
                    messages=[
                        {"role": "user", "content": f"""
                        Analyze the quality of the following code and rate it on a scale of 0-100 
                        with 0 being extremely poor quality code (unreadable, unmaintainable) and 100 being perfect quality code (clean, well-structured, well-documented).
                        
                        Rules for scoring:
                        1. Score should be a multiple of 5 (e.g., 65, 70, 75)
                        2. Perfect or near-perfect code should get a score of 95-100
                        3. Extremely poor quality code should get a score of 0-5
                        4. Average code should be scored around 50-55
                        
                        Consider factors like readability, maintainability, code organization, variable naming, and adherence to best practices.
                        
                        Identify the top quality concerns if any exist. For each concern:
                        1. Provide the exact line number(s) where the issue occurs
                        2. Briefly explain the quality issue
                        3. Suggest a better approach
                        
                        Format your response as a JSON object with the following structure:
                        {{
                            "score": <number between 0-100 in multiples of 5>,
                            "concerns": [
                                "Line <line_number>: <brief description of issue> - <suggested improvement>",
                                "Lines <start_line>-<end_line>: <brief description of issue> - <suggested improvement>",
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
                print(f"API call error in quality evaluation: {e}")
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
                print("Quality evaluation timed out")
                return {"score": "50", "concerns": ["Analysis timed out"]}
    
    except Exception as e:
        print(f"Error analyzing quality: {e}")
        return {"score": "50", "concerns": [f"Error: {str(e)}"]}

if __name__ == "__main__":
    # Example usage
    sample_code = """
def example_function():
    return sum(range(100))
    """
    quality_analysis = evaluate_quality(sample_code)
    print(f"Quality Analysis:\n{quality_analysis}")
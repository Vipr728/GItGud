from openai import OpenAI
from dotenv import load_dotenv
import os

#LOAD API KEYS
load_dotenv()
APIKEY = os.getenv("NVIDIA_NIM_API_KEY_EFFICIENCY")


def evaluate_efficiency(code: str) -> str:
    """Analyze the efficiency of the given code using DeepSeek AI."""

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=APIKEY,
    )

    try:
        completion = client.chat.completions.create(
            model="deepseek-ai/deepseek-r1-distill-qwen-7b",
            messages=[
                {"role": "user", "content": f"""
                Analyze the efficiency of the following code and rate it on a scale of 0-100 
                 with 0 being completely disfunctional and 100 being perfectly optimized with no room for improvement.
                 Output just the number between 0 and 100 inclusive, no other information. Just the number.:\n{code}"""}
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
        print(f"Error analyzing efficiency: {e}")
        return "Error occurred during analysis."

if __name__ == "__main__":
    # Example usage
    sample_code = """
def example_function():
    return sum(range(100))
    """
    efficiency_analysis = evaluate_efficiency(sample_code)
    print(f"Efficiency Analysis:\n{efficiency_analysis}")
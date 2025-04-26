from openai import OpenAI
from dotenv import load_dotenv
import os
#LOAD API KEYS
load_dotenv()
APIKEY = os.getenv("NVIDIA_NIM_API_KEY_EFFICIENCY")


def evaluate_efficiency(code: str) -> int:
        #TODO: make calculate

    client = OpenAI(
      base_url = "https://integrate.api.nvidia.com/v1",
      api_key = APIKEY,
    )

    completion = client.chat.completions.create(
      model="deepseek-ai/deepseek-r1-distill-qwen-7b",
      messages=[{"role":"user","content":("tell me the efficiency of the following code"+ code)}],
      temperature=0.6,
      top_p=0.7,
      max_tokens=4096,
      stream=True
    )

    for chunk in completion:
      if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")

if __name__ == "__main__":
    # Example usage
    sample_code = """
def example_function():
    return sum(range(100))
    """
    efficiency_score = evaluate_efficiency(sample_code)
    print(f"Efficiency Score: {efficiency_score}")
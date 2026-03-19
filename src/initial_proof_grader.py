import os
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

BASE_DIR = Path(__file__).resolve().parents[1]

MODEL = "google/gemini-3-pro-preview"  # Adjust model as needed

CANDIDATE_PATH = "candidates-pipeline/q4.md"
# CANDIDATE_PATH = "candidates-misc/q4_claude.md"
SOLUTION_FILE = "4-sol.pdf"
PROBLEM_FILE = "q4.tex"


# CANDIDATE_PATH = "candidates-misc/q6.md"
# SOLUTION_FILE = "6-sol.pdf"
# PROBLEM_FILE = "q6.tex"


# CANDIDATE_PATH = "candidates-pipeline/q10.md"# <did this one first
CANDIDATE_PATH = "candidates-misc/q10_claude.md"
SOLUTION_FILE = "10-sol.pdf"
PROBLEM_FILE = "q10.tex"

print(f"basedir: {BASE_DIR}")

# Load files
grader_prompt = (BASE_DIR / "prompts/grader.md").read_text()
problem_text = (BASE_DIR / "benchmarks/first-proof/problems"/PROBLEM_FILE).read_text()
candidate_text = (BASE_DIR / "candidates"/CANDIDATE_PATH).read_text()
solution_pdf_path = BASE_DIR / "benchmarks/first-proof/solutions" / SOLUTION_FILE
solution_b64 = base64.standard_b64encode(solution_pdf_path.read_bytes()).decode()

# Fill prompt placeholders
prompt = grader_prompt.replace("{problem_statement}", problem_text) \
                      .replace("{student_answer}", candidate_text)

# Build API request with PDF attachment
response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json",
    },
    json={
        "model": MODEL,
        "max_tokens": 16000,
        "reasoning": {
            "effort": "high",
        },
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt.replace("{solution}", f"[see attached PDF {SOLUTION_FILE} for ground-truth solution]")},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:application/pdf;base64,{solution_b64}"
                        },
                    },
                ],
            }
        ],
    },
)

## Check response
if response.status_code != 200:
    print(f"API request failed with status {response.status_code}")
    print(response.text)
    exit(1)

data = response.json()

if "error" in data:
    print(f"API error: {data['error']}")
    exit(1)

if not data.get("choices"):
    print(f"Unexpected response format: {data}")
    exit(1)

result = data["choices"][0]["message"]["content"]

if not result:
    print("Warning: empty response content")
    print(f"Full response: {data}")
    exit(1)

# Save result
results_dir = BASE_DIR / "results"
results_dir.mkdir(exist_ok=True)
output_path = results_dir / f"{PROBLEM_FILE.replace('.tex', '_grading.md')}"
output_path.write_text(result)
print(f"Grading saved to {output_path}")

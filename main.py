import os
import subprocess 
import sys
from pathlib import Path

from strands import Agent, tool
from strands.models.gemini import GeminiModel

#Project Settings

#test pilot folder, ai will be able to inspect files inside folder
PROJECT_ROOT = Path(__file__).parent.resolve()

#folder of generated or private files, agent doesnt inspect them
IGNORED_FOLDERS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
}

#files agent inspects
ALLOWED_FILE_TYPES = {
    ".py",
    ".toml",
    ".md",
    ".txt",
}

def get_safe_path(relative_path: str) -> Path:
    """Return a safe path that's inside this project"""

    #Combine the project folder and requested path
    candidate = (PROJECT_ROOT / relative_path).resolve()

    #Block paths such as private-file.txt
    if candidate != PROJECT_ROOT and PROJECT_ROOT not in candidate.parents:
        raise ValueError(
            "Access outside the project folder not allowed"
        )

    return candidate



#TOOL 1: Listing Project Files

@tool
def list_project_files() -> str:
    """List readable source and test files in the project."""

    discovered_files = []

    for path in PROJECT_ROOT.rglob("*"):
        #Skip .venv, .git and cache folders
        if any(folder in path.parts for folder in IGNORED_FOLDERS):
            continue

        #Show only the allowed file tyoes
        if path.is_file() and path.suffix in ALLOWED_FILE_TYPES:
            relative_path = path.relative_to(PROJECT_ROOT)
            discovered_files.append(str(relative_path))

    if not discovered_files:
        return "No readable project files were found"

    return "\n".join(sorted(discovered_files))



#TOOL 2: Read One File

@tool
def read_project_file(relative_path: str) -> str:
    """Read one source or test file

    Args:
        relative_path: File path relative to the project root, 
        such as sample_app/calculator.py
    """

    try:
        path = get_safe_path(relative_path)
    except ValueError as error:
        return f"ERROR: {error}"

    if not path.exists():
        return f"ERROR: {relative_path} does not exist"

    if not path.is_file():
        return f"ERROR {relative_path} is not a file"

    if path.suffix not in ALLOWED_FILE_TYPES:
        return f"ERROR: Reading {path.suffix} files is not allowed"

    content = path.read_text(encoding="utf-8")

    #Limit the text sent to Gemini
    #reduces unnescessary toxen usage
    return content[:12_000]



#Tool 3: Run Pytest

#Store the pytest result after the first run. This prevents Gemini from repeatedly running the same tests.
PYTEST_RESULT_CACHE: str | None = None

@tool
def run_python_tests() -> str:
    """Run pytest once and return the results.

    This tool should only be called once during an investigation.
    """

    global PYTEST_RESULT_CACHE

    # JOT: If pytest already ran, do not run it again.
    if PYTEST_RESULT_CACHE is not None:
        print(
            "[TestPilot] Pytest already ran. Using cached result.",
            flush=True,
        )

        return (
            "PYTEST HAS ALREADY RUN.\n"
            "Do not call this tool again.\n"
            "Use the earlier pytest result and write the final report now."
        )

    print("[TestPilot] Running pytest...", flush=True)

    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        output = completed.stdout + completed.stderr

        PYTEST_RESULT_CACHE = (
            f"PYTEST EXIT CODE: {completed.returncode}\n\n"
            f"PYTEST OUTPUT:\n{output[:12_000]}\n\n"
            "IMPORTANT: Pytest has finished. Do not call any more tools. "
            "Write the final TestPilot report now."
        )

        return PYTEST_RESULT_CACHE

    except subprocess.TimeoutExpired:
        PYTEST_RESULT_CACHE = (
            "ERROR: Tests exceeded the 30-second limit.\n"
            "Do not call this tool again. Write the final report."
        )

        return PYTEST_RESULT_CACHE

    except Exception as error:
        PYTEST_RESULT_CACHE = (
            f"ERROR: Tests could not run: {error}\n"
            "Do not call this tool again. Write the final report."
        )

        return PYTEST_RESULT_CACHE



#GEMINI MODEL 

model = GeminiModel(
    client_args={
        #Read the key from the terminal environment, real key not here
        "api_key": os.environ["GEMINI_API_KEY"],
    },
    model_id="gemini-3.1-flash-lite",

    #A low temperature makes tool use more predictable.
    params={
        "temperature": 0.1,
        "max_output_tokens": 2500,
    },
)



#TESTPILOT AGENT

agent = Agent(
    name="testpilot",
    description="Inspects Python projects and diagnoses test failures",
    model=model,

    #prevent strands from printing partial output
    #we'll print the completed report ourseleves
    retry_strategy=None,

    #Only actions the agent can perform
    tools=[
        list_project_files,
        read_project_file,
        run_python_tests,
    ],

    #This is the agents permanent job description
    system_prompt="""
You are TestPilot, a careful Python testing and debugging agent.

You have a strict tool budget:

- Call list_project_files only once.
- Read sample_app/calculator.py only once.
- Read tests/test_calculator.py only once.
- Call run_python_tests only once.
- After receiving the pytest result, stop calling tools.
- Immediately produce the final written report.

Follow this exact order:

1. Call list_project_files.
2. Read sample_app/calculator.py.
3. Read tests/test_calculator.py.
4. Call run_python_tests one time.
5. Analyze the pytest result.
6. Produce the final report.

Format the final response as:

PROBLEM:
EVIDENCE:
ROOT CAUSE:
PROPOSED FIX:
RISK:
TESTS TO RERUN:

Rules:

- Never run pytest more than once.
- Never read the same file more than once.
- Never invent file contents.
- Never claim tests passed unless pytest returned exit code 0.
- Mention the relevant filenames and functions.
- Explain the problem in beginner-friendly language.
- Do not claim that you edited a file.
- You may propose code, but you cannot apply it.
""",
)



#START TESTPILOT

result = agent(
    """
Inspect This Python Project.

Run the tests, explain why they fail and propose the smallest fixes. 
Use the availanle tools instead of guessing.
""",
limits={
    "turns": 8,
    "output_tokens": 2500,
    "total_tokens": 20_000,
},
)

print("\n========== FINAL TESTPILOT REPORT ==========\n")
print(result)
print(f"\nStop reason: {result.stop_reason}")
# TestPilot AI

TestPilot AI is an agentic Python software-testing and debugging platform built with Python, uv, Strands Agents and Gemini. Gemini was chosen over other models such as AWS due to to his accesible and free tiers

## Current milestone

Milestone 1 implements a safe diagnostic agent that can:

- Inspect project files
- Read Python source code and tests
- Run pytest
- Analyze failing tests
- Explain root causes
- Propose corrections

The agent can't edit source code in this milestone

## Demo project

The calculator application currently contains deliberate bugs. These bugs are included to demonstrate that TestPilot can discover and explain test failures


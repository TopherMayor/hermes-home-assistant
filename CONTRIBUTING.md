# Contributing to Hermes Home Assistant

Thank you for your interest in contributing! Here's everything you need to know.

## Getting Started

### Prerequisites

- Home Assistant 2025.1.0 or later
- Hermes Agent with API server platform enabled
- Python 3.11+ for local development

### Development Setup

```bash
# Clone the repository
git clone https://github.com/TopherMayor/hermes-home-assistant.git
cd hermes-home-assistant

# Set up a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dev dependencies
pip install ruff flake8 mypy pytest pytest-asyncio pytest-cov \
    aioresponses types-aiohttp types-python-dateutil

# Run linting
ruff check .
flake8 custom_components/hermes_assistant/ --max-line-length=100
mypy custom_components/hermes_assistant/ --ignore-missing-imports

# Run tests
pytest tests/ -v
```

## Project Structure

```
custom_components/hermes_assistant/
├── __init__.py      # Services + platform setup
├── api.py           # Hermes API client (HTTP, streaming, errors)
├── config_flow.py   # Config entries UI
├── const.py         # Constants (domain, defaults)
├── conversation.py  # Assist conversation agent
├── sensor.py        # Gateway health sensors
├── manifest.json    # HA integration metadata
└── www/
    └── hermes-chat-card.js   # Lovelace chat card
```

## Making Changes

### Branch Naming

- `feat/` — new features
- `fix/` — bug fixes
- `docs/` — documentation
- `refactor/` — code refactoring
- `test/` — adding or updating tests

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(sensor): add connection quality metric
fix(conversation): handle empty message gracefully
docs(readme): clarify API key setup steps
```

### Pull Request Process

1. **Fork** the repository and create a feature branch
2. **Run linting** (`ruff check .`) and tests (`pytest tests/`)
3. **Describe changes** clearly in the PR description
4. **Link any related issues** using `Fixes #123` or `Relates to #456`
5. Request review from `@TopherMayor`

## Code Standards

- **Type hints** required on all function signatures
- **Docstrings** on all public classes and functions
- **No trailing whitespace**, use Python 3.11 syntax
- **Error handling**: always catch specific exceptions, never bare `except:`
- **No dead code**: remove commented-out blocks before merging

## Testing

All new features must include tests. Run:

```bash
# All tests with coverage
pytest tests/ -v --cov=custom_components/hermes_assistant --cov-report=term-missing

# Single test file
pytest tests/test_api.py -v
```

## Reporting Issues

- Use the [Bug Report template](./.github/ISSUE_TEMPLATE/bug_report.yml) for bugs
- Use the [Feature Request template](./.github/ISSUE_TEMPLATE/feature_request.yml) for ideas
- Use the [Config Help template](./.github/ISSUE_TEMPLATE/config_help.yml) for setup issues

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
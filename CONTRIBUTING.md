# Contributing

1. Fork, create a branch, and set up a venv: `pip install -r requirements.txt pytest ruff`.
2. Make your change with tests where practical (tests must run offline).
3. Run `ruff check . && ruff format . && pytest`.
4. Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:` ...) and open a pull request.

Please never include real scripts, audio, `.env` files or tokens in a PR. See [AGENTS.md](AGENTS.md) for the architecture overview.

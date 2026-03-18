# Project Rules

- Python project management must be done with `uv`.
- Development environment: Windows. Use powershell to run commands.
- The program should run as a standalone watcher that detects changes in the input DOCX and regenerates the output.
- The program must include a web server to serve the `output/` directory.
- The web server must automatically reload the page when the contents of `output/` change.
- **Debug Scripts**: All temporary debug scripts should be stored in the `tmp/` directory at the project root for ad-hoc troubleshooting.

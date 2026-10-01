# E2B LibreOffice Code Interpreter Template

This builds a custom E2B template based on `code-interpreter-v1` and adds:

- `poppler-utils`
- `libreoffice`

The build script reads `E2B_API_KEY` from the repository `.env` file. Keep
`E2B_BASE_TEMPLATE=code-interpreter-v1` for the upstream base template and set
`E2B_TEMPLATE=code-interpreter-v1-libreoffice` so the backend uses the custom
template when `sandbox_provider` is `e2b`.

```bash
./.venv/bin/pip install "e2b>=2.14.0" "e2b-code-interpreter>=2.5.0"
./.venv/bin/python scripts/e2b/build_libreoffice_template.py --smoke-test
```

To force a rebuild without E2B's template cache:

```bash
./.venv/bin/python scripts/e2b/build_libreoffice_template.py --skip-cache --smoke-test
```

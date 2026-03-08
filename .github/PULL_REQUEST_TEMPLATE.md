# Pull Request Template for Mattin AI Repository

Thank you for contributing to MattinAI! Please fill in the sections below to help the maintainers understand your changes and review your pull request effectively. All pull requests should be clearly scoped and well documented.

## Description

Provide a concise summary of the changes included in this pull request and explain the rationale for them. Describe what problem you are trying to solve or what feature you are adding. If this pull request fixes a bug, clearly describe the bug and how your change resolves it.

## Related Issue(s)

Link to any existing issues or discussions that are related to this pull request. Use GitHub keywords to automatically close issues when the pull request is merged (e.g. `Fixes #42`). If there is no related issue, briefly explain why a new issue was not created.

## Type of Change

Please check the option that best describes the purpose of this pull request:

* [ ] Bug fix (a change that does not break existing functionality and fixes an issue)
* [ ] Feature (a change that does not break existing functionality and adds new functionality)
* [ ] Documentation (updates or adds documentation only)
* [ ] Refactor (code change that neither fixes a bug nor adds a feature)
* [ ] Performance improvement
* [ ] Test (adding or updating tests)
* [ ] Build or infrastructure (changes to tooling, deployment scripts, CI/CD, etc.)

## Dependencies Added

List any new libraries or packages that this pull request introduces. For backend changes, include new Python modules or additions to the `pyproject.toml. For frontend changes, mention any new TypeScript dependencies added to `package.json`. If no new libraries have been added, state “None”.

## Affected Components

Indicate whether your changes impact the backend (FastAPI), the frontend (React), or both. This helps reviewers involve the appropriate maintainers. If the changes span multiple services or shared modules, please mention them here.

## Implementation Details

Describe any important implementation details, design decisions, or assumptions that reviewers should be aware of. Include information about any new dependencies, environment variables, configuration files, or data migration steps. If the pull request affects the API or user interfaces, outline the changes and provide examples where appropriate.

## How to Test

Explain how reviewers can verify that your changes work as intended. Include step by step instructions for setting up the environment, running tests, or reproducing the bug. If the change impacts the frontend, consider including screenshots or screen recordings to illustrate the new behaviour.

## Checklist
Before submitting, please confirm that you have completed the following. Replace the empty square brackets with an `x` to indicate completion.

* [ ] All commits in this pull request are signed using GPG, as required by our commit signing policy (see `.github/instructions/.gh-commit.instructions.md`).
* [ ] I have read the contributing guidelines and my change adheres to the coding standards of this project (see `docs/README.md#contributing`).
* [ ] I have added tests that prove my fix or feature works, or confirm that tests are not needed for this change.
* [ ] I have run all existing tests and they all pass locally.
* [ ] I have updated any relevant documentation, configuration files, or environment examples as needed.
* [ ] I have considered backwards compatibility and ensured that my change does not break existing functionality.
* [ ] For UI changes, I have included relevant screenshots or screencasts.

## Additional Notes

Include any other information that reviewers might find useful, such as known limitations, follow up work, or dependencies on other pull requests. If there are breaking changes or deprecations introduced by this pull request, clearly call them out here.
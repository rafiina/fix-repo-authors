# fix-repo-authors

Script to update the name and e-mail on commits

## Install

### Linux

```sh
git clone https://github.com/rafiina/fix-repo-authors.git
cd fix-repo-authors
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### Windows

Something similar to Linux.  I'm sure you can figure it out or I'll add it later.

## Usage

```sh
python3 fix-repo-authors
```

Just follow the prompts

## Other notes

You will need your SSH Key setup for your repository provider.  Doing all repos at once is only supported on github, and only for users.

## Todo

- Support orgs on github
- Support enterprise github instances
- Refactor so it's not one ugly file, maybe
- Align prompts -- The all repos path is cleaner
- Better output formatting
- Optimizations:
  - If hitting all repos, only update a repo if it has the selected name/email
  - Option to cache ssh key passphrase in memory for current execution
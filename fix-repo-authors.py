from dataclasses import dataclass, field
import os
import pathlib
import pprint
import re
from shutil import which, rmtree
import stat
import subprocess
from typing import TypeVar

import requests

T = TypeVar("T")


def command_installed(name) -> pathlib.Path | None:

    path = which(name)
    if path is not None:
        path = pathlib.Path(path)
    return path


def user_prompt_yes_no(prompt: str) -> bool:
    return user_prompt(prompt=prompt, options={"Yes": True, "No": False})


def user_prompt(prompt: str, options: dict[str, T], option_seperator: str = ", ") -> T:
    print()
    option_count = range(1, len(options.keys()) + 1)
    prompt_options = dict(zip(option_count, options.keys()))
    prompt_options_text = option_seperator.join(
        [f"{option} - {label}" for option, label in prompt_options.items()]
    )
    answer = input(f"{prompt}\n{prompt_options_text}:\n")

    while not answer.isnumeric() and answer not in option_count:
        answer = input(f"{prompt}\n{prompt_options_text}:\n")

    chosen_option = prompt_options[int(answer)]

    return options[chosen_option]


def ensure_exists(file: pathlib.Path) -> bool:
    exists = file.exists()
    if not exists:
        wants_to_download = user_prompt_yes_no(
            f"{file.as_posix()} was not found.  Would you like to download?"
        )
        if wants_to_download:
            download_git_filter_repo(file)
        exists = file.exists()
    else:
        wants_to_use_existing = user_prompt_yes_no(
            f"{file.as_posix()} exists. Would you like to use this one?"
        )
        exists = wants_to_use_existing

    return exists


def download_git_filter_repo(path: pathlib.Path) -> bool:

    url = (
        "https://raw.githubusercontent.com/newren/git-filter-repo/main/git-filter-repo"
    )
    try:
        resp = requests.get(url)
        path.write_bytes(resp.content)
    except:
        return False

    return True


def ensure_executable(file: pathlib.Path) -> bool:
    is_executable = os.access(file, os.X_OK)
    if not is_executable:
        wants_to_execute = user_prompt_yes_no(
            f"{file.as_posix()} is not executable.  Would you like to make it so?"
        )
        if wants_to_execute:
            st = os.stat(file)
            os.chmod(file, st.st_mode | stat.S_IEXEC)
        is_executable = os.access(file, os.X_OK)

    return is_executable


@dataclass
class GitRepo:
    name: str
    ssh_url: str
    origin: str = field(init=False)
    names_updated: list[str] = field(default_factory=list)
    emails_updated: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.origin = self.ssh_url


class GitClient:
    def __init__(
        self, git_filter_repo_path: pathlib.Path, base_working_dir: pathlib.Path
    ) -> None:
        self._git_filter_repo_path = git_filter_repo_path
        self._working_dir = base_working_dir / "repo-update-working_dir"
        self._working_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_repo_list(cls, github_user: str) -> list[GitRepo]:
        api = f"https://api.github.com/users/{github_user}/repos"
        response: list[dict] = requests.get(api).json()

        repo_list = [
            GitRepo(repo["name"].strip(), repo["ssh_url"].strip()) for repo in response
        ]
        return repo_list

    def clone(self, repo: GitRepo) -> None:
        os.chdir(self._working_dir)
        repo_dir = self._working_dir / repo.name
        if (repo_dir).exists():
            delete_dir = user_prompt_yes_no(
                f"The repo {repo.name} already exists.  Do you want to delete it?"
            )
            if delete_dir:
                rmtree(repo_dir)
                subprocess.run(["git", "clone", repo.ssh_url, repo.name])
        else:
            subprocess.run(["git", "clone", repo.ssh_url, repo.name])

    def get_origin(self, repo: GitRepo) -> str:
        os.chdir(self._working_dir / repo.name)
        process = subprocess.run(
            ["git", "remote", "get-url", "--all", "origin"], capture_output=True
        )
        return process.stdout.decode().strip()

    def set_origin(self, repo: GitRepo, origin: str) -> None:
        os.chdir(self._working_dir / repo.name)
        if self.get_origin(repo):
            subprocess.run(["git", "remote", "set-url", "origin", origin])
        else:
            subprocess.run(["git", "remote", "add", "origin", origin])

    def push(self, repo: GitRepo) -> None:
        os.chdir(self._working_dir / repo.name)
        self.set_origin(repo, repo.origin)
        subprocess.run(["git", "push", "--all", "--force"])

    def get_all_authors(self, repo: GitRepo) -> list[tuple[str, str]]:
        os.chdir(self._working_dir / repo.name)
        process = subprocess.run(["git", "shortlog", "-sne"], capture_output=True)
        output = process.stdout.decode().strip().split("\n")
        count_removed = [author.split("\t")[1] for author in output]

        extract_name_and_email = re.compile("(.*) <(.*)>")
        results = [
            re.fullmatch(extract_name_and_email, author_info)
            for author_info in count_removed
        ]
        ret = [
            (str(result.groups()[0]), str(result.groups()[1]))
            for result in results
            if result is not None
        ]

        return ret

    def update_name(self, repo: GitRepo, old: str, new: str) -> None:
        os.chdir(self._working_dir / repo.name)
        callback = f'return name if name != b"{old}" else b"{new}"'
        subprocess.run([self._git_filter_repo_path, "--name-callback", callback])
        self.set_origin(repo, repo.origin)

    def update_email(self, repo: GitRepo, old: str, new: str) -> None:
        os.chdir(self._working_dir / repo.name)
        subprocess.run(
            [
                self._git_filter_repo_path,
                "--email-callback",
                f'return email if email !=b"{old}" else b"{new}"',
            ]
        )
        self.set_origin(repo, repo.origin)


def handle_names(client: GitClient, repo: GitRepo) -> None:
    prompt = (
        f"Do you want to update a name for all branches in repository '{repo.name}'?"
    )
    done = False
    while not done:
        authors = client.get_all_authors(repo)
        print(f"Current authors on repo:\n {authors}")
        answer = user_prompt_yes_no(prompt)
        if answer:
            old_name = input("What is the name you would like to change?\n")
            new_name = input("What is the name you would like to replace it with?\n")
            client.update_name(repo, old_name, new_name)
            repo.names_updated.append(new_name)
        else:
            done = True


def handle_emails(client: GitClient, repo: GitRepo) -> None:
    prompt = (
        f"Do you want to update an email for all branches in repository '{repo.name}'?"
    )
    done = False
    while not done:
        authors = client.get_all_authors(repo)
        print(f"Current authors on repo:\n {authors}")
        answer = user_prompt_yes_no(prompt)
        if answer:
            old_name = input("What is the email you would like to change?\n")
            new_name = input("What is the email you would like to replace it with?\n")
            client.update_email(repo, old_name, new_name)
            repo.emails_updated.append(new_name)
        else:
            done = True


def update_repo(*, client: GitClient, automatic_push: bool = False) -> None:
    name = input("What is the repo name?\n")
    clone_url = input("What is the repo url?\n")

    repo = GitRepo(name, clone_url)

    client.clone(repo)
    handle_names(client, repo)
    handle_emails(client, repo)

    push_changes = automatic_push
    if not automatic_push:
        prompt = f"Do you want to push changes for repo {repo.name}?"
        push_changes = user_prompt_yes_no(prompt)

    if push_changes:
        client.push(repo)

    print(f"Updates complete for repo {repo.name}")
    names = "\n".join([name for name in repo.names_updated])
    print(f"Updated Names:\n {names}")
    emails = "\n".join([email for email in repo.emails_updated])
    print(f"Updated Emails:\n {emails}")
    authors = client.get_all_authors(repo)
    print(f"Current authors on repo:\n {authors}")


def update_all_repos(*, client: GitClient, automatic_push: bool = False) -> None:
    github_user = input("What is the github username?\n")
    repos = client.get_repo_list(github_user)

    for repo in repos:
        client.clone(repo)

    names: set[str] = set()
    emails: set[str] = set()
    done = False
    while not done:
        names = set()
        emails = set()
        for repo in repos:
            repo_authors = client.get_all_authors(repo)
            for author in repo_authors:
                name, email = author
                names.add(name)
                emails.add(email)

        name_options = {
            f"{name} (name)": {"type": "name", "name": name} for name in names
        }
        email_options = {
            f"{email} (email)": {"type": "email", "email": email} for email in emails
        }
        quit_option = {"quit": {"type": "quit"}}
        prompt = "Please choose a name or email to change.\n"
        item_to_replace = user_prompt(
            prompt, {**name_options, **email_options, **quit_option}, "\n"
        )
        new_value = ""
        if item_to_replace["type"] != "quit":
            new_value = input("What would you like to change it to? ")

        for repo in repos:
            if item_to_replace["type"] == "quit":
                done = True
                break
            elif item_to_replace["type"] == "email":
                client.update_email(repo, item_to_replace["email"], new_value)
            elif item_to_replace["type"] == "name":
                client.update_name(repo, item_to_replace["name"], new_value)

    for repo in repos:
        print(f"\n{repo.name} author details:\n")
        pprint.pprint(client.get_all_authors(repo))

    if not automatic_push:
        for repo in repos:
            push_repo = user_prompt_yes_no(
                f"Would you like to push changes for {repo.name}?"
            )
            if push_repo:
                client.push(repo)
    else:
        for repo in repos:
            print(f"Pushing {repo.name}")
            client.push(repo)


def main() -> None:
    install_name = "git-filter-repo"
    install_path = command_installed(install_name)
    if not install_path:
        install_path = pathlib.Path(f"{pathlib.Path.cwd()}") / install_name
        ensure_exists(install_path)
        ensure_executable(install_path)

    print(
        "You will be prompted for your credentials for each interaction with git that requires them."
    )
    prompt = "Do you want to automatically push changes to your git remote?"
    automatic_push = user_prompt_yes_no(prompt)
    prompt = "Do you want to update one repository or all respositories for a user (github only)?"
    options = {"One Repo": update_repo, "All Repos (github only)": update_all_repos}

    clone_dir = pathlib.Path.cwd() / "fresh-repos"
    git_client = GitClient(install_path, clone_dir)
    call_back = user_prompt(prompt, options)
    call_back(client=git_client, automatic_push=automatic_push)


def test() -> None:
    pass


if __name__ == "__main__":
    main()

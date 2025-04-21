import re
import Code_Smells_Detection.Extract_Files.GitHubFileModel as GitHubFileModel
import Code_Smells_Detection.Extract_Files.Save_Http_Request as Request


def extract_github_pr_details(pr_url: str):
    """
    Extracts OWNER, REPO, and PR_NUMBER from a GitHub PR URL.

    Example URL: https://github.com/microsoft/vscode/pull/1234
    Returns: ('microsoft', 'vscode', 1234)
    """
    pattern = r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.match(pattern, pr_url)

    if match:
        owner, repo, pr_number = match.groups()
        return owner, repo, int(pr_number)
    else:
        raise ValueError("Invalid GitHub PR URL format")


def validate_http_request(content, url, get_data=None):
    if content.status_code == 200:
        return get_data(content) if get_data is not None else content
    else:
        raise Exception(f"❌ HTTP request failed: {url} with code: {content.status_code}")


def get_file_by_sha(OWNER, REPO, sha: str, file_path):
    file_url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{sha}/{file_path}"
    file_content = Request.get(
        url_api=file_url,
        get_data=lambda content:
        GitHubFileModel.get_GitHubFileModel_by_content(
            content=content,
            sha=sha,
            file_path=file_path
        ))

    return file_content


def get_changed_file_names_in_PR(OWNER, REPO, PR_NUMBER):
    files_url = f"https://api.github.com/repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}/files"
    files = Request.get(files_url)

    return [file["filename"] for file in files]


def get_PR_content(OWNER, REPO, PR_NUMBER):
    pr_url = f"https://api.github.com/repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}"
    pr_data = Request.get(pr_url)

    return pr_data


def get_changed_files_in_PR(pr_url: str):
    files_before_PR = []
    files_after_PR = []

    OWNER, REPO, PR_NUMBER = extract_github_pr_details(pr_url)

    pr_data = get_PR_content(OWNER, REPO, PR_NUMBER)

    # Get base (before PR) and head (after PR) branches
    base_sha = pr_data["base"]["sha"]  # Commit SHA before PR
    head_sha = pr_data["head"]["sha"]  # Commit SHA after PR

    changed_file_names = get_changed_file_names_in_PR(OWNER, REPO, PR_NUMBER)

    for file_path in changed_file_names:

        base_file_content = get_file_by_sha(OWNER, REPO, base_sha, file_path)
        head_file_content = get_file_by_sha(OWNER, REPO, head_sha, file_path)

        files_before_PR.append(base_file_content)
        files_after_PR.append(head_file_content)

    return files_before_PR, files_after_PR


if __name__ == '__main__':
    pr_url = "https://github.com/yakovelmaleh/Master/pull/317"
    files_before_PR, files_after_PR = get_changed_files_in_PR(pr_url)
    print(len(files_before_PR))

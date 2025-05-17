import os
import uuid

def get_file_name_and_type(file_url: str):
    file_path = file_url.split("/")[-1]

    # Get the file extension
    ext = os.path.splitext(file_path)[1].lower()
    file_name = os.path.splitext(file_path)[0].lower()

    # Map common extensions to programming languages
    file_types = {
        ".py": "Python",
        ".java": "Java",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".cpp": "C++",
        ".c": "C",
        ".cs": "C#",
        ".go": "Go",
        ".rb": "Ruby",
        ".php": "PHP",
        ".html": "HTML",
        ".css": "CSS",
        ".json": "JSON",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".xml": "XML",
        ".sh": "Shell Script",
        ".md": "Markdown",
    }

    return file_name, file_types.get(ext, "Unknown"), ext


class GitHubFileModel:
    def __init__(self, file_name: str, data: str, file_type_name: str, file_type_suffix: str, url: str, content, sha: str=None, file_path: str=None):
        self.file_name = file_name
        self.file_path = file_path
        self.data = data
        self.file_type_name = file_type_name
        self.sha = sha
        self.url = url
        self.file_type_suffix = file_type_suffix

    def save_as_file(self, save_path: str):
        if self.file_type_suffix == "Unknown":
            raise Exception("This file is invalid.")

        unique_suffix = str(uuid.uuid4())[:8]  # Use first 8 characters of UUID for brevity
        file_name = f"{self.file_name}_{unique_suffix}{self.file_type_suffix}"

        file_path = os.path.join(save_path, file_name)

        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(self.data)


def get_GitHubFileModel_by_content(content, file_path=None, sha=None) -> GitHubFileModel:
    url = content.url
    data = content.text
    file_name, file_type_name, file_type_suffix = get_file_name_and_type(url)

    return GitHubFileModel(
        file_name=file_name,
        data=data,
        file_type_name=file_type_name,
        file_type_suffix=file_type_suffix,
        url=url,
        content=content,
        sha=sha,
        file_path=file_path
    )



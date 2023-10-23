#!/usr/bin/env python
"""
This syncs markdown files from a file or folder to Confluence as child pages
of a given parent, with their docstring, HTML formatted.
It uses v2 of the Confluence API, and can exclude files.
If selecting a single file, it assumes the file you want to sync is in the main repo dir.
"""

import os
import sys
import requests
from markdown_it import MarkdownIt
from requests.exceptions import RequestException

def load_environment_variables():
    """
    Load environment variables and check for required values.
    """
    env_var_names = [
        "cloud",
        "user",
        "token",
        "parent_page_id",
        "space_id",
    ]

    envs = {}
    for var_name in env_var_names:
        envs[var_name] = os.environ.get(var_name)
        if not envs[var_name]:
            print(f"Missing value for {var_name}")
            sys.exit(1)

    if "input_file" in os.environ:
        envs["input_file"] = os.environ["input_file"]
    if "input_md_directory" in os.environ:
        envs["input_md_directory"] = os.environ["input_md_directory"]
    if "exclude_files" in os.environ:
        envs["exclude_files"] = os.environ["exclude_files"]

    return envs

def process_directory(envs, links):
    """
    Process a directory of markdown files.
    """
    md_directory = os.path.join(
        os.environ["GITHUB_WORKSPACE"], envs["input_md_directory"]
    )
    if envs.get("exclude_files"):
        exclude_files = envs["exclude_files"].split(",")
    else:
        exclude_files = []

    for root, _, files in os.walk(md_directory):
        for f in files:
            if f.endswith(".md") and f not in exclude_files:
                md_file = os.path.join(root, f)
                links = process_file(md_file, envs, links)

    return links


def process_file(md_file, envs, links):
    """
    The real main function. This processes each file
    and compares the markdown file content to 
    existing, if any.
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            md = f.read()

        markdown = MarkdownIt()
        html = markdown.render(md)
        page_title = os.path.splitext(os.path.basename(md_file))[0]

        page_info = find_page_by_title(page_title, envs)

        if page_info["current_version"]:
            new_version = page_info["current_version"] + 1
        else:
            new_version = None

        if page_info["page_id"]:
            # Compare existing content with the new content
            if html != page_info["existing_content"]:
                # Content has changed, update it
                update_url = f"https://{envs['cloud']}.atlassian.net/wiki/api/v2/pages/{page_info['page_id']}"
                update_content = {
                    "id": page_info["page_id"],
                    "status": "current",
                    "version": {"number": new_version},
                    "title": page_title,
                    "body": {"value": html, "representation": "storage"},
                }

                headers = {"Content-Type": "application/json"}
                auth = (envs["user"], envs["token"])

                update_response = requests.put(
                    update_url,
                    json=update_content,
                    auth=auth,
                    headers=headers,
                    timeout=10,
                )
                if update_response.status_code == 200:
                    updated_link = (
                        f"https://{envs['cloud']}.atlassian.net/wiki"
                        + update_response.json()["_links"]["webui"]
                    )
                    links.append(f"{page_title}: {updated_link}")
                    print(f"{page_title}: Content update successful. New version: {new_version}")
                else:
                    print(
                        f"{page_title}: Failed. HTTP status code: {update_response.status_code}"
                    )
            else:
                # Content is the same, no need to update
                print(f"{page_title}: Identical content, no update required.")
        else:
            # Construct the Confluence Rest API URL
            url = f"https://{envs['cloud']}.atlassian.net/wiki/api/v2/pages"
            content = {
                "spaceId": envs["space_id"],
                "status": "current",
                "title": page_title,
                "parentId": envs["parent_page_id"],
                "body": {"value": html, "representation": "storage"},
            }
            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            auth = (envs["user"], envs["token"])

            response = requests.post(
                url,
                json=content,
                auth=auth,
                headers=headers,
                timeout=10,
            )

            if response.status_code == 200:
                link = (
                    f"https://{envs['cloud']}.atlassian.net/wiki"
                    + response.json()["_links"]["webui"]
                )
                links.append(f"{page_title}: {link}")
                print(f"{page_title}: Content upload successful.")
            else:
                print(
                    f"{page_title}: Failed. HTTP status code: {response.status_code}"
                )
    except RequestException as e:
        print(f"An error occurred during the HTTP request: {e}")
        sys.exit(1)

    return links




def find_page_by_title(page_title, envs):
    """
    Find a Confluence page by title.
    """
    url = f"https://{envs['cloud']}.atlassian.net/wiki/api/v2/pages"
    params = {
        "title": page_title,
    }
    headers = {"Accept": "application/json"}
    response = requests.get(
        url, params=params, auth=(envs["user"], envs["token"]), headers=headers, timeout=10,
    )
    if response.status_code == 200:
        data = response.json()
        if data.get("results"):
            page_id = data["results"][0]["id"]
            version_number = data["results"][0]["version"]["number"]
            existing_content = data["results"][0]["body"]["storage"]
            return page_id, version_number, existing_content

    return None, None

def main():
    """
    Main function that orchestrates it all
    """
    envs = load_environment_variables()

    links = []
    if "input_file" in envs:
        # Process a single file
        single_file = os.path.join(os.environ["GITHUB_WORKSPACE"], envs["input_file"])
        links = process_file(single_file, envs, links)
    elif "input_md_directory" in envs:
        # Process a directory of markdown files
        links = process_directory(envs, links)
    else:
        # Handle the case where neither are provided
        print("No specific input provided.")
        sys.exit(1)

    print(links)

if __name__ == "__main__":
    main()

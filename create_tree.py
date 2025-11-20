#!/usr/bin/env python3

import argparse
import yaml
import subprocess
import os
import logging
import re
from pathlib import Path
from git import Repo, GitCommandError

def load_yaml(filename):
    with open(filename, 'r') as f:
        return yaml.safe_load(f)

def save_yaml(data, filename):
    with open(filename, 'w') as f:
        yaml.dump(data, f, default_flow_style=False)

def sanitize_for_filename(s):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', s)

def get_latest_mbox_by_msg_id(initial_msgid, base_log_file, topic, tag, debug=False):
    log_dir = os.path.dirname(base_log_file)
    base_name = os.path.splitext(os.path.basename(base_log_file))[0]
    sanitized_msgid = sanitize_for_filename(initial_msgid)
    unique_log_file = os.path.join(log_dir, f"{base_name}_{topic}_{sanitized_msgid}.log")
    branch_name = f"{tag}/{topic}"

    command = [
        'b4', 'shazam', '--merge-base', tag, '-H', '-l', initial_msgid
    ]
    logging.info(f"Patch message ID {initial_msgid}")
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)

        with open(unique_log_file, 'a') as log_f:
            log_f.write('\n' + '='*20 + ' b4 shazam STDOUT start ' + '='*20 + '\n')
            log_f.write(result.stdout)
            log_f.write('\n' + '='*20 + ' b4 shazam STDOUT end ' + '='*20 + '\n')
            log_f.write('\n' + '='*20 + ' b4 shazam STDERR start ' + '='*20 + '\n')
            log_f.write(result.stderr)
            log_f.write('\n' + '='*20 + ' b4 shazam STDERR end ' + '='*20 + '\n')

        thread_found = re.search(r'Grabbing thread from .*?\/([^\/]+@.*?)\/t\.mbox\.gz', result.stderr)
        new_ver = re.search(r'Will use the latest revision:\s*v\d+', result.stderr)

        if thread_found:
            latest_msgid = thread_found.group(1)

            if new_ver:
                link_match = re.search(r'Link:\s+https?://lore\.kernel\.org/r/([^>\s]+)', result.stderr)
                if link_match:
                    latest_msgid = link_match.group(1)

            if debug:
                logging.debug(f"thread_found.group(1) = {thread_found.group(1)}, new_ver = {new_ver.group(0) if new_ver else 'None'}, latest_msgid = {latest_msgid}")

            logging.info(f"Patch message ID {'(unchanged)' if not new_ver else '(updated)'}: {latest_msgid}")

            #co_cmd = ['git', 'checkout', 'FETCH_HEAD', '-b', branch_name]
            #co_result = subprocess.run(co_cmd, capture_output=True, text=True)

            #with open(unique_log_file, 'a') as log_f:
            #    log_f.write('\n' + '='*20 + ' git checkout STDOUT start ' + '='*20 + '\n')
            #    log_f.write(co_result.stdout)
            #    log_f.write('\n' + '='*20 + ' git checkout STDOUT end ' + '='*20 + '\n')
            #    log_f.write('\n' + '='*20 + ' git checkout STDERR start ' + '='*20 + '\n')
            #    log_f.write(co_result.stderr)
            #    log_f.write('\n' + '='*20 + ' git checkout STDERR end ' + '='*20 + '\n')

            #if co_result.returncode == 0:
            #    logging.info(f"Checked out FETCH_HEAD as branch {branch_name}")
            #else:
            #    logging.error(f"Failed to checkout FETCH_HEAD as branch {branch_name}; see log")
            return True, latest_msgid

        logging.warning(f"Could not parse latest patch message ID from b4 output (see {unique_log_file}).")
        return False, initial_msgid

    except subprocess.CalledProcessError as e:
        logging.error(f"Error running b4 command for {initial_msgid}: {e.stderr}")
        return False, initial_msgid

def restore_git_state_to_pristine(repo):
    rebase_apply_path = os.path.join('.git', 'rebase-apply')
    if os.path.exists(rebase_apply_path):
        logging.info("Detected incomplete git am or git rebase operation.")
        try:
            repo.git.am('--abort')
        except GitCommandError:
            pass
        try:
            repo.git.rebase('--abort')
        except GitCommandError:
            pass
        logging.info("Aborted lingering git am or git rebase operation.")

def run_b4_shazam_apply(message_id, repo, log_file):
    restore_git_state_to_pristine(repo)
    cmd = ['b4', 'shazam', message_id]
    with open(log_file, 'a') as log_f:
        result = subprocess.run(cmd, stdout=log_f, stderr=log_f, text=True)
    if result.returncode != 0:
        logging.error(f"Failed to apply patchset {message_id}; see log.")
        return False
    logging.info(f"Applied patchset {message_id}")
    return True

def checkout_branch(repo, branch_name, base_tag):
    try:
        repo.git.checkout('-b', branch_name, base_tag)
        logging.info(f"Created and checked out branch: {branch_name} at {base_tag}")
    except GitCommandError as e:
        if "already exists" in str(e):
            logging.info(f"Branch {branch_name} already exists. Resetting to {base_tag} and checking out.")
            try:
                repo.git.checkout(branch_name)
                repo.git.reset('--hard', base_tag)
            except GitCommandError as e2:
                logging.error(f"Failed to reset branch {branch_name} to {base_tag}: {e2}")
                return False
        else:
            logging.error(f"Failed to checkout branch {branch_name}: {e}")
            return False
    return True

def repo_state(repo):
    is_clean = not (repo.is_dirty(untracked_files=True))
    git_dir = Path(repo.git_dir)
    states = {}
    states['rebase'] = (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()
    states['merge'] = (git_dir / "MERGE_HEAD").exists()
    states['cherry_pick'] = (git_dir / "CHERRY_PICK_HEAD").exists()
    states['revert'] = (git_dir / "REVERT_HEAD").exists()
    states['am'] = (git_dir / "AM_HEAD").exists()
    states['bisect'] = (git_dir / "BISECT_LOG").exists()
    return {
        "is_clean": is_clean,
        "special_states": {k: v for k, v in states.items() if v}
    }

def main():
    parser = argparse.ArgumentParser(
        description="Create git topic branches with latest b4 patches from message IDs YAML.")
    parser.add_argument('yaml_file', help='Path to the YAML file with message IDs')
    parser.add_argument('tag', help='Git tag to base branches on and use as branch prefix')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    yaml_path = os.path.abspath(args.yaml_file)
    yaml_dir = os.path.dirname(yaml_path)
    yaml_base = os.path.splitext(os.path.basename(yaml_path))[0]
    log_file = os.path.join(yaml_dir, yaml_base + '.log')

    logging_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        filename=log_file,
        filemode='w',
        level=logging_level,
        format='%(asctime)s %(levelname)s %(message)s'
    )

    repo = Repo('.')
    status = repo_state(repo)
    if not status["is_clean"]:
        logging.error("Working tree or index is not clean. Please clean, commit, or stash your changes.")
        exit(1)
    if status["special_states"]:
        logging.error(f"Repo is mid-operation: {status['special_states']}")
        exit(1)

    logging.info(f"Logging output to: {log_file}")

    topics = load_yaml(args.yaml_file)
    updated_topics = {}

    for topic, msg_ids in topics.items():
        updated_msg_ids = []
        for msg_id in msg_ids:
            success, final_msg_id = get_latest_mbox_by_msg_id(msg_id, log_file, topic, args.tag, args.debug)
            if not success:
                logging.warning(f"Could not fetch/apply latest patchset for {msg_id}. Using original message ID.")
            logging.warning(f"Patchset for {msg_id}.")
            updated_msg_ids.append(final_msg_id)
        updated_topics[topic] = updated_msg_ids

    output_file = os.path.join(yaml_dir, yaml_base + '_new.yaml')
    save_yaml(updated_topics, output_file)
    logging.info(f"Updated YAML saved to {output_file}")

    # Uncomment this block to enable branch checkout and patch application:
    # for topic, msg_ids in updated_topics.items():
    #     if not checkout_branch(repo, args.tag, args.tag):
    #         logging.error(f"Aborting due to failure checking out tag {args.tag}")
    #         return
    #t
    #     branch_name = f'{args.tag}/{topic}'
    #     if not checkout_branch(repo, branch_name, args.tag):
    #         continue
    #
    #     for msg_id in msg_ids:
    #         if not run_b4_shazam_apply(msg_id, repo, log_file):
    #             logging.warning(f"Skipping patchset {msg_id} due to apply failure")
    #
    #     checkout_branch(repo, 'main', None)

if __name__ == "__main__":
    main()

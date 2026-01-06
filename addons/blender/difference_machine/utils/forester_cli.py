"""
Forester CLI wrapper for Difference Machine addon.
Provides functions to execute forester CLI commands and parse their output.
"""

import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from .config_loader import get_forester_path, validate_forester_path

logger = logging.getLogger(__name__)


class ForesterCLIError(Exception):
    """Exception raised when forester CLI command fails."""
    pass


class ForesterCLI:
    """Wrapper for forester CLI commands."""
    
    def __init__(self):
        self._forester_path: Optional[str] = None
        self._cached_path: Optional[str] = None
    
    @property
    def forester_path(self) -> Optional[str]:
        """Get forester executable path, loading from config if needed."""
        if self._forester_path is None:
            self._forester_path = get_forester_path()
        return self._forester_path
    
    def _execute_command(
        self,
        command: List[str],
        cwd: Optional[Path] = None,
        timeout: Optional[int] = 30
    ) -> Tuple[int, str, str]:
        """
        Execute forester CLI command.
        
        Args:
            command: Command and arguments as list
            cwd: Working directory for command execution
            timeout: Timeout in seconds (None for no timeout)
            
        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        forester_path = self.forester_path
        if not forester_path:
            raise ForesterCLIError("Forester executable path not configured")
        
        is_valid, error_msg = validate_forester_path(forester_path)
        if not is_valid:
            raise ForesterCLIError(error_msg)
        
        full_command = [forester_path] + command
        
        try:
            result = subprocess.run(
                full_command,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            raise ForesterCLIError(f"Command timed out after {timeout} seconds")
        except Exception as e:
            raise ForesterCLIError(f"Failed to execute command: {str(e)}")
    
    def init(self, repo_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Initialize a new forester repository.
        
        Args:
            repo_path: Path to repository root
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            exit_code, stdout, stderr = self._execute_command(
                ["init", str(repo_path)],
                cwd=repo_path.parent
            )
            
            if exit_code == 0:
                return True, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, error_msg
        except ForesterCLIError as e:
            return False, str(e)
    
    def status(self, repo_path: Path) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Get repository status.
        
        Args:
            repo_path: Path to repository root
            
        Returns:
            Tuple of (success, status_data, error_message)
            status_data contains: branch, head, modified, deleted, untracked
        """
        try:
            exit_code, stdout, stderr = self._execute_command(
                ["status"],
                cwd=repo_path
            )
            
            if exit_code != 0:
                error_msg = stderr.strip() or "Unknown error"
                return False, None, error_msg
            
            # Parse status output
            status_data = self._parse_status_output(stdout)
            return True, status_data, None
        except ForesterCLIError as e:
            return False, None, str(e)
    
    def _parse_status_output(self, output: str) -> Dict[str, Any]:
        """Parse status command output."""
        status = {
            "branch": "main",
            "head": None,
            "modified": [],
            "deleted": [],
            "untracked": [],
            "clean": False
        }
        
        lines = output.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith("On branch "):
                status["branch"] = line.replace("On branch ", "").strip()
            elif line.startswith("HEAD: "):
                status["head"] = line.replace("HEAD: ", "").strip()
            elif line == "Nothing to commit, working tree clean":
                status["clean"] = True
            elif line == "No commits yet":
                status["head"] = None
            elif line == "Modified files:":
                current_section = "modified"
            elif line == "Deleted files:":
                current_section = "deleted"
            elif line == "Untracked files:":
                current_section = "untracked"
            elif line.startswith("  ") and current_section:
                # File entry (indented with 2 spaces)
                file_path = line.strip()
                if file_path:
                    status[current_section].append(file_path)
        
        return status
    
    def log(self, repo_path: Path, branch: Optional[str] = None, limit: int = 100) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Get commit history.
        
        Args:
            repo_path: Path to repository root
            branch: Branch name (optional, defaults to current)
            limit: Maximum number of commits to return
            
        Returns:
            Tuple of (success, commits_list, error_message)
        """
        try:
            command = ["log"]
            if branch:
                command.append(branch)
            
            exit_code, stdout, stderr = self._execute_command(
                command,
                cwd=repo_path
            )
            
            if exit_code != 0:
                error_msg = stderr.strip() or "Unknown error"
                return False, None, error_msg
            
            if "No commits yet" in stdout:
                return True, [], None
            
            # Parse log output
            commits = self._parse_log_output(stdout)
            return True, commits[:limit], None
        except ForesterCLIError as e:
            return False, None, str(e)
    
    def _parse_log_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse log command output."""
        commits = []
        current_commit = None
        
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            if line.startswith("commit "):
                # Save previous commit
                if current_commit:
                    commits.append(current_commit)
                
                # Start new commit
                commit_hash = line.replace("commit ", "").strip()
                current_commit = {
                    "hash": commit_hash,
                    "author": None,
                    "date": None,
                    "message": None,
                    "tag": None,
                    "is_head": False
                }
            elif line.startswith("HEAD:") and current_commit:
                # Parse HEAD indicator
                if "true" in line.lower():
                    current_commit["is_head"] = True
            elif line.startswith("Author: ") and current_commit:
                current_commit["author"] = line.replace("Author: ", "").strip()
            elif line.startswith("Date:   ") and current_commit:
                date_str = line.replace("Date:   ", "").strip()
                current_commit["date"] = date_str
            elif line.startswith("Tag:    ") and current_commit:
                current_commit["tag"] = line.replace("Tag:    ", "").strip()
            elif current_commit and current_commit["message"] is None:
                # First non-empty line after date/tag is message
                if line and not line.startswith("commit ") and not line.startswith("Author:") and not line.startswith("Date:") and not line.startswith("Tag:") and not line.startswith("HEAD:"):
                    current_commit["message"] = line.strip()
        
        # Add last commit
        if current_commit:
            commits.append(current_commit)
        
        return commits
    
    def branch(self, repo_path: Path, action: str = "list", branch_name: Optional[str] = None) -> Tuple[bool, Optional[Any], Optional[str]]:
        """
        List, create, or delete branches.
        
        Args:
            repo_path: Path to repository root
            action: "list", "create", or "delete"
            branch_name: Branch name (required for create/delete)
            
        Returns:
            Tuple of (success, result, error_message)
            For list: result is list of branch dicts with name and is_current
            For create/delete: result is None
        """
        # Validate inputs
        if not repo_path:
            return False, None, "Repository path is required"
        if not isinstance(repo_path, Path):
            repo_path = Path(repo_path)
        if action not in ("list", "create", "delete"):
            return False, None, f"Invalid action: {action}. Must be 'list', 'create', or 'delete'"
        
        try:
            if action == "list":
                exit_code, stdout, stderr = self._execute_command(
                    ["branch"],
                    cwd=repo_path
                )
                
                if exit_code != 0:
                    error_msg = stderr.strip() or "Unknown error"
                    return False, None, error_msg
                
                branches = self._parse_branch_list_output(stdout)
                return True, branches, None
            
            elif action == "create":
                if not branch_name or not branch_name.strip():
                    return False, None, "Branch name required"
                
                branch_name = branch_name.strip()
                exit_code, stdout, stderr = self._execute_command(
                    ["branch", branch_name],
                    cwd=repo_path
                )
                
                if exit_code == 0:
                    return True, None, None
                else:
                    error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                    return False, None, error_msg
            
            elif action == "delete":
                if not branch_name or not branch_name.strip():
                    return False, None, "Branch name required"
                
                branch_name = branch_name.strip()
                exit_code, stdout, stderr = self._execute_command(
                    ["branch", "-d", branch_name],
                    cwd=repo_path
                )
                
                if exit_code == 0:
                    return True, None, None
                else:
                    error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                    return False, None, error_msg
            
            else:
                return False, None, f"Unknown action: {action}"
        except ForesterCLIError as e:
            return False, None, str(e)
    
    def _parse_branch_list_output(self, output: str) -> List[Dict[str, str]]:
        """Parse branch list output."""
        branches = []
        
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            is_current = line.startswith("* ")
            branch_name = line.replace("* ", "").replace("  ", "").strip()
            
            if branch_name:
                branches.append({
                    "name": branch_name,
                    "is_current": is_current
                })
        
        return branches
    
    def checkout(self, repo_path: Path, branch_or_commit: str) -> Tuple[bool, Optional[str]]:
        """
        Checkout a branch or commit.
        
        Args:
            repo_path: Path to repository root
            branch_or_commit: Branch name or commit hash
            
        Returns:
            Tuple of (success, error_message)
        """
        # Validate inputs
        if not repo_path:
            return False, "Repository path is required"
        if not isinstance(repo_path, Path):
            repo_path = Path(repo_path)
        if not branch_or_commit or not branch_or_commit.strip():
            return False, "Branch or commit name is required"
        
        try:
            exit_code, stdout, stderr = self._execute_command(
                ["checkout", branch_or_commit.strip()],
                cwd=repo_path
            )
            
            if exit_code == 0:
                return True, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, error_msg
        except ForesterCLIError as e:
            return False, str(e)
    
    def stash(self, repo_path: Path, action: str = "save", message: Optional[str] = None) -> Tuple[bool, Optional[Any], Optional[str]]:
        """
        Stash operations: save, list, pop, apply, drop.
        
        Args:
            repo_path: Path to repository root
            action: Action to perform: "save", "list", "pop", "apply", "drop"
            message: Message for stash save (optional)
            
        Returns:
            Tuple of (success, result_data, error_message)
            For "save": (success, stash_hash, error_message)
            For "list": (success, list_of_stashes, error_message)
            For others: (success, None, error_message)
        """
        try:
            if action == "save":
                cmd = ["stash", "save"]
                if message:
                    cmd.append(message)
            elif action == "list":
                cmd = ["stash", "list"]
            elif action in ["pop", "apply", "drop"]:
                cmd = ["stash", action]
                if message:  # For drop/pop/apply, message is the stash hash
                    cmd.append(message)
            else:
                return False, None, f"Unknown stash action: {action}"
            
            exit_code, stdout, stderr = self._execute_command(cmd, cwd=repo_path)
            
            if exit_code == 0:
                if action == "save":
                    # Parse stash hash from output like "Saved stash abc12345"
                    stash_hash = None
                    for line in stdout.split('\n'):
                        if 'Saved stash' in line:
                            parts = line.split()
                            if len(parts) >= 3:
                                stash_hash = parts[2]
                                break
                    return True, stash_hash, None
                elif action == "list":
                    # Parse stash list
                    stashes = []
                    for line in stdout.split('\n'):
                        line = line.strip()
                        if line.startswith('stash{'):
                            # Format: stash{abc12345}: message
                            try:
                                hash_end = line.find('}')
                                if hash_end > 0:
                                    stash_hash = line[6:hash_end]
                                    stash_message = line[hash_end + 2:].strip() if len(line) > hash_end + 2 else ""
                                    stashes.append({"hash": stash_hash, "message": stash_message})
                            except (IndexError, ValueError) as e:
                                logger.debug(f"Failed to parse stash line '{line}': {e}")
                            except Exception as e:
                                logger.warning(f"Unexpected error parsing stash line '{line}': {e}")
                    return True, stashes, None
                else:
                    return True, None, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, None, error_msg
        except ForesterCLIError as e:
            return False, None, str(e)
    
    def stash_pop(self, repo_path: Path, stash_hash: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Pop a stash (apply and remove).
        
        Args:
            repo_path: Path to repository root
            stash_hash: Stash hash (optional, uses latest if not provided)
            
        Returns:
            Tuple of (success, error_message)
        """
        cmd = ["stash", "pop"]
        if stash_hash:
            cmd.append(stash_hash)
        try:
            exit_code, stdout, stderr = self._execute_command(cmd, cwd=repo_path)
            if exit_code == 0:
                return True, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, error_msg
        except ForesterCLIError as e:
            return False, str(e)
    
    def stash_apply(self, repo_path: Path, stash_hash: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Apply a stash (keep stash).
        
        Args:
            repo_path: Path to repository root
            stash_hash: Stash hash (optional, uses latest if not provided)
            
        Returns:
            Tuple of (success, error_message)
        """
        cmd = ["stash", "apply"]
        if stash_hash:
            cmd.append(stash_hash)
        try:
            exit_code, stdout, stderr = self._execute_command(cmd, cwd=repo_path)
            if exit_code == 0:
                return True, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, error_msg
        except ForesterCLIError as e:
            return False, str(e)
    
    def commit(
        self,
        repo_path: Path,
        message: str,
        author: Optional[str] = None,
        tag: Optional[str] = None,
        no_verify: bool = False
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Create a commit.
        
        Args:
            repo_path: Path to repository root
            message: Commit message
            author: Author name (optional)
            tag: Tag name (optional)
            no_verify: Skip pre-commit and post-commit hooks (optional)
            
        Returns:
            Tuple of (success, commit_hash, error_message)
        """
        # Validate inputs
        if not repo_path:
            return False, None, "Repository path is required"
        if not isinstance(repo_path, Path):
            repo_path = Path(repo_path)
        if not message or not message.strip():
            return False, None, "Commit message cannot be empty"
        
        try:
            command = ["commit", "-m", message.strip()]
            
            if author:
                command.extend(["--author", author])
            
            if tag:
                command.extend(["--tag", tag])
            
            if no_verify:
                command.append("--no-verify")
            
            exit_code, stdout, stderr = self._execute_command(
                command,
                cwd=repo_path,
                timeout=60  # Commits can take longer
            )
            
            if exit_code == 0:
                # Try to extract commit hash from output
                # Format: [branch hash] message
                commit_hash = None
                for line in stdout.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Check for format: [branch hash] message
                    if line.startswith('[') and ']' in line:
                        # Extract hash from [branch hash] format
                        bracket_end = line.find(']')
                        if bracket_end > 0:
                            bracket_content = line[1:bracket_end]
                            parts = bracket_content.split()
                            if len(parts) >= 2:
                                # Second part should be the hash
                                potential_hash = parts[1]
                                if len(potential_hash) >= 8 and all(c in '0123456789abcdef' for c in potential_hash.lower()):
                                    commit_hash = potential_hash
                                    break
                    
                    # Fallback: look for hash-like strings
                    if not commit_hash:
                        parts = line.split()
                        for part in parts:
                            if len(part) >= 8 and all(c in '0123456789abcdef' for c in part.lower()):
                                commit_hash = part
                                break
                        if commit_hash:
                            break
                
                return True, commit_hash, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, None, error_msg
        except ForesterCLIError as e:
            return False, None, str(e)
    
    def show(self, repo_path: Path, commit_hash: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Show commit details.
        
        Args:
            repo_path: Path to repository root
            commit_hash: Commit hash
            
        Returns:
            Tuple of (success, commit_data, error_message)
        """
        # Validate inputs
        if not repo_path:
            return False, None, "Repository path is required"
        if not isinstance(repo_path, Path):
            repo_path = Path(repo_path)
        if not commit_hash or not commit_hash.strip():
            return False, None, "Commit hash is required"
        
        try:
            exit_code, stdout, stderr = self._execute_command(
                ["show", commit_hash.strip()],
                cwd=repo_path
            )
            
            if exit_code != 0:
                error_msg = stderr.strip() or "Unknown error"
                return False, None, error_msg
            
            # Parse show output
            commit_data = self._parse_show_output(stdout)
            return True, commit_data, None
        except ForesterCLIError as e:
            return False, None, str(e)
    
    def _parse_show_output(self, output: str) -> Dict[str, Any]:
        """Parse show command output."""
        commit_data = {
            "hash": None,
            "author": None,
            "date": None,
            "message": None,
            "parent": None,
            "tree": None,
            "type": None,
            "files": []
        }
        
        lines = output.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith("commit "):
                commit_data["hash"] = line.replace("commit ", "").strip()
            elif line.startswith("Author: "):
                commit_data["author"] = line.replace("Author: ", "").strip()
            elif line.startswith("Date:   "):
                commit_data["date"] = line.replace("Date:   ", "").strip()
            elif line.startswith("Parent: "):
                commit_data["parent"] = line.replace("Parent: ", "").strip()
            elif line.startswith("Tree: "):
                commit_data["tree"] = line.replace("Tree: ", "").strip()
            elif line.startswith("Type: "):
                commit_data["type"] = line.replace("Type: ", "").strip()
            elif line == "Files:":
                current_section = "files"
            elif current_section == "files" and line:
                commit_data["files"].append(line)
            elif commit_data["message"] is None and not any(line.startswith(prefix) for prefix in ["commit ", "Author:", "Date:", "Parent:", "Tree:", "Type:", "Files:"]):
                # Message line
                if commit_data["message"]:
                    commit_data["message"] += " " + line
                else:
                    commit_data["message"] = line
        
        return commit_data
    
    def gc(self, repo_path: Path, dry_run: bool = False, reflog_expire_days: int = 90) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Run garbage collection.
        
        Args:
            repo_path: Path to repository root
            dry_run: If True, only show what would be deleted without actually deleting
            reflog_expire_days: Number of days to keep commits in reflog before deletion
            
        Returns:
            Tuple of (success, stats, error_message)
            stats contains: commits_deleted, trees_deleted, blobs_deleted
        """
        try:
            command = ["gc"]
            if dry_run:
                command.append("--dry-run")
            if reflog_expire_days != 90:
                command.extend(["--reflog-expire", str(reflog_expire_days)])
            
            exit_code, stdout, stderr = self._execute_command(
                command,
                cwd=repo_path,
                timeout=300  # GC can take a while
            )
            
            if exit_code != 0:
                error_msg = stderr.strip() or "Unknown error"
                return False, None, error_msg
            
            # Parse GC output
            stats = self._parse_gc_output(stdout)
            return True, stats, None
        except ForesterCLIError as e:
            return False, None, str(e)
    
    def _parse_gc_output(self, output: str) -> Dict[str, int]:
        """Parse garbage collection output."""
        stats = {
            "commits_deleted": 0,
            "trees_deleted": 0,
            "blobs_deleted": 0,
            "meshes_deleted": 0
        }
        
        for line in output.split('\n'):
            line = line.strip()
            if "Commits deleted:" in line:
                try:
                    stats["commits_deleted"] = int(line.split(":")[-1].strip())
                except (ValueError, IndexError) as e:
                    logger.debug(f"Failed to parse commits_deleted from line '{line}': {e}")
            elif "Trees deleted:" in line:
                try:
                    stats["trees_deleted"] = int(line.split(":")[-1].strip())
                except (ValueError, IndexError) as e:
                    logger.debug(f"Failed to parse trees_deleted from line '{line}': {e}")
            elif "Blobs deleted:" in line:
                try:
                    stats["blobs_deleted"] = int(line.split(":")[-1].strip())
                except (ValueError, IndexError) as e:
                    logger.debug(f"Failed to parse blobs_deleted from line '{line}': {e}")
            elif "Meshes deleted:" in line:
                try:
                    stats["meshes_deleted"] = int(line.split(":")[-1].strip())
                except (ValueError, IndexError) as e:
                    logger.debug(f"Failed to parse meshes_deleted from line '{line}': {e}")
        
        return stats
    
    def rebuild(self, repo_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Rebuild database from storage.
        
        Args:
            repo_path: Path to repository root
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            exit_code, stdout, stderr = self._execute_command(
                ["rebuild"],
                cwd=repo_path,
                timeout=600  # Rebuild can take a long time
            )
            
            if exit_code == 0:
                return True, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, error_msg
        except ForesterCLIError as e:
            return False, str(e)
    
    def delete_commit(self, repo_path: Path, commit_hash: str) -> Tuple[bool, Optional[str]]:
        """
        Delete a commit.
        
        Args:
            repo_path: Path to repository root
            commit_hash: Hash of commit to delete
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            exit_code, stdout, stderr = self._execute_command(
                ["commit", "--delete", commit_hash],
                cwd=repo_path
            )
            
            if exit_code == 0:
                return True, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, error_msg
        except ForesterCLIError as e:
            return False, str(e)
    
    def diff(self, repo_path: Path, commit1_hash: Optional[str] = None, commit2_hash: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Show differences between commits or working directory.
        
        Args:
            repo_path: Path to repository root
            commit1_hash: First commit hash (optional, compares with HEAD if not provided)
            commit2_hash: Second commit hash (optional, compares with working directory if not provided)
            
        Returns:
            Tuple of (success, diff_output, error_message)
        """
        try:
            command = ["diff"]
            if commit1_hash:
                command.append(commit1_hash)
            if commit2_hash:
                command.append(commit2_hash)
            
            exit_code, stdout, stderr = self._execute_command(
                command,
                cwd=repo_path
            )
            
            if exit_code == 0:
                return True, stdout, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, None, error_msg
        except ForesterCLIError as e:
            return False, None, str(e)
    
    def compare(self, repo_path: Path, commit_hash: str, editor_path: Optional[str] = None, cleanup: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Compare a commit by checking it out to a temporary directory.
        
        Args:
            repo_path: Path to repository root
            commit_hash: Hash of commit to compare
            editor_path: Optional path to editor executable to launch
            cleanup: If True, clean up the temporary comparison directory
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            command = ["compare", commit_hash]
            if cleanup:
                command.append("--cleanup")
            if editor_path:
                command.extend(["--editor", editor_path])
            
            exit_code, stdout, stderr = self._execute_command(
                command,
                cwd=repo_path
            )
            
            if exit_code == 0:
                return True, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, error_msg
        except ForesterCLIError as e:
            return False, str(e)
    
    def list_locks(self, repo_path: Path) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        List all file locks in current branch.
        
        Args:
            repo_path: Path to repository root
            
        Returns:
            Tuple of (success, locks_list, error_message)
            locks_list contains: file_path, lock_type, user, expires_at
        """
        try:
            exit_code, stdout, stderr = self._execute_command(
                ["lock", "list"],
                cwd=repo_path
            )
            
            if exit_code != 0:
                error_msg = stderr.strip() or "Unknown error"
                return False, None, error_msg
            
            if "No locks found" in stdout:
                return True, [], None
            
            # Parse lock output
            locks = self._parse_lock_list_output(stdout)
            return True, locks, None
        except ForesterCLIError as e:
            return False, None, str(e)
    
    def _parse_lock_list_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse lock list command output."""
        locks = []
        in_locks_section = False
        
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            if line == 'Locks:':
                in_locks_section = True
                continue
            
            if in_locks_section and line:
                # Parse: file_path (exclusive/shared) by user expires: date
                lock_info = {
                    'file_path': '',
                    'lock_type': 'exclusive',
                    'user': '',
                    'expires_at': None
                }
                
                if ' by ' in line:
                    parts = line.split(' by ')
                    file_part = parts[0].strip()
                    user_part = parts[1].strip() if len(parts) > 1 else ''
                    
                    # Extract file path and lock type
                    if ' (exclusive)' in file_part:
                        lock_info['file_path'] = file_part.replace(' (exclusive)', '').strip()
                        lock_info['lock_type'] = 'exclusive'
                    elif ' (shared)' in file_part:
                        lock_info['file_path'] = file_part.replace(' (shared)', '').strip()
                        lock_info['lock_type'] = 'shared'
                    else:
                        lock_info['file_path'] = file_part
                    
                    # Extract user and expiration
                    if ' expires: ' in user_part:
                        exp_parts = user_part.split(' expires: ')
                        lock_info['user'] = exp_parts[0].strip()
                        try:
                            from datetime import datetime
                            dt = datetime.strptime(exp_parts[1].strip(), "%Y-%m-%d %H:%M:%S")
                            lock_info['expires_at'] = dt.timestamp()
                        except Exception:
                            pass
                    else:
                        lock_info['user'] = user_part
                    
                    locks.append(lock_info)
        
        return locks
    
    def lock_file(self, repo_path: Path, file_path: str, exclusive: bool = True, expire_hours: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        """
        Lock a file.
        
        Args:
            repo_path: Path to repository root
            file_path: Path to file to lock (relative to repo root)
            exclusive: If True, exclusive lock; if False, shared lock
            expire_hours: Optional expiration time in hours
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            command = ["lock", file_path]
            if exclusive:
                command.append("--exclusive")
            else:
                command.append("--shared")
            if expire_hours and expire_hours > 0:
                command.extend(["--expire", str(expire_hours)])
            
            exit_code, stdout, stderr = self._execute_command(
                command,
                cwd=repo_path
            )
            
            if exit_code == 0:
                return True, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, error_msg
        except ForesterCLIError as e:
            return False, str(e)
    
    def unlock_file(self, repo_path: Path, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Unlock a file.
        
        Args:
            repo_path: Path to repository root
            file_path: Path to file to unlock (relative to repo root)
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            exit_code, stdout, stderr = self._execute_command(
                ["lock", "unlock", file_path],
                cwd=repo_path
            )
            
            if exit_code == 0:
                return True, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, error_msg
        except ForesterCLIError as e:
            return False, str(e)
    
    def add(self, repo_path: Path, files: Optional[List[str]] = None) -> Tuple[bool, Optional[str]]:
        """
        Add files to staging area.
        
        Args:
            repo_path: Path to repository root
            files: List of file paths to add (optional, defaults to "." to add all files)
            
        Returns:
            Tuple of (success, error_message)
        """
        # Validate inputs
        if not repo_path:
            return False, "Repository path is required"
        if not isinstance(repo_path, Path):
            repo_path = Path(repo_path)
        
        try:
            command = ["add"]
            if files:
                command.extend(files)
            else:
                command.append(".")  # Add all files by default
            
            exit_code, stdout, stderr = self._execute_command(
                command,
                cwd=repo_path
            )
            
            if exit_code == 0:
                return True, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, error_msg
        except ForesterCLIError as e:
            return False, str(e)
    
    def list_tags(self, repo_path: Path) -> Tuple[bool, Optional[List[str]], Optional[str]]:
        """
        List all tags.
        
        Args:
            repo_path: Path to repository root
            
        Returns:
            Tuple of (success, tags_list, error_message)
        """
        try:
            exit_code, stdout, stderr = self._execute_command(
                ["tag"],
                cwd=repo_path
            )
            
            if exit_code == 0:
                tags = []
                for line in stdout.strip().split('\n'):
                    line = line.strip()
                    if line:
                        tags.append(line)
                return True, tags, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, None, error_msg
        except ForesterCLIError as e:
            return False, None, str(e)
    
    def delete_tag(self, repo_path: Path, tag_name: str) -> Tuple[bool, Optional[str]]:
        """
        Delete a tag.
        
        Args:
            repo_path: Path to repository root
            tag_name: Name of the tag to delete
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            exit_code, stdout, stderr = self._execute_command(
                ["tag", "--delete", tag_name],
                cwd=repo_path
            )
            
            if exit_code == 0:
                return True, None
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                return False, error_msg
        except ForesterCLIError as e:
            return False, str(e)


# Global instance
_cli_instance: Optional[ForesterCLI] = None


def get_cli() -> ForesterCLI:
    """Get global ForesterCLI instance."""
    global _cli_instance
    if _cli_instance is None:
        _cli_instance = ForesterCLI()
    return _cli_instance

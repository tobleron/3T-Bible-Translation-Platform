import os
import datetime
import shutil
import re

class SessionManager:
    """Manages session folders, files, and history."""
    def __init__(self, config, session_to_load=None):
        self.config = config
        self._setup_directories()

        if session_to_load:
            self.session_id = session_to_load
        else:
            self.session_id = f"session_{datetime.datetime.now().strftime('%d%m%Y_%H%M%S')}"

        self.session_path = os.path.join(self.config['sessions_directory'], self.session_id)

        # If this is a new session, create the directory for it.
        if not session_to_load:
            os.makedirs(self.session_path, exist_ok=True)

        sorted_ids = self._get_sorted_exchange_ids()
        self.next_seq_id = sorted_ids[-1] + 1 if sorted_ids else 1


    def _setup_directories(self):
        os.makedirs(self.config['sessions_directory'], exist_ok=True)
        os.makedirs(self.config['static_prompts_directory'], exist_ok=True)
        os.makedirs(self.config['saved_responses_directory'], exist_ok=True)

    @staticmethod
    def list_sessions(config):
        """Lists all available sessions, sorted from newest to oldest."""
        sessions_dir = config['sessions_directory']
        if not os.path.exists(sessions_dir):
            return []
        
        sessions = [d for d in os.listdir(sessions_dir) if os.path.isdir(os.path.join(sessions_dir, d)) and d.startswith('session_')]
        
        def get_datetime_from_session(session_name):
            try:
                # session_DDMMYYYY_HHMMSS_OptionalLabel -> need to extract the date/time part
                return datetime.datetime.strptime(f"{session_name.split('_')[1]}_{session_name.split('_')[2]}", "%d%m%Y_%H%M%S")
            except (ValueError, IndexError):
                return datetime.datetime.min # Put malformed names at the end
        
        sessions.sort(key=get_datetime_from_session, reverse=True)
        return sessions
    
    def is_session_empty(self, session_id):
        """Check if a session directory contains no prompt files."""
        session_path = os.path.join(self.config['sessions_directory'], session_id)
        if not os.path.isdir(session_path):
            return True # If it doesn't exist, it's "empty"
        for item in os.listdir(session_path):
            if item.startswith("prompt_") and item.endswith(".txt"):
                return False # Found a prompt file
        return True

    def prune_sessions(self, dry_run=True):
        """Finds or deletes sessions that are empty or unlabeled."""
        all_sessions = self.list_sessions(self.config)
        sessions_to_delete = []
        deleted_sessions = []

        for session_id in all_sessions:
            if session_id == self.session_id:
                continue # Never prune the active session

            is_unlabeled = len(session_id.split('_')) == 3
            is_empty = self.is_session_empty(session_id)

            if is_unlabeled or is_empty:
                sessions_to_delete.append(session_id)

        if dry_run:
            return sessions_to_delete

        for session_id in sessions_to_delete:
            try:
                path_to_delete = os.path.join(self.config['sessions_directory'], session_id)
                shutil.rmtree(path_to_delete)
                deleted_sessions.append(session_id)
            except OSError:
                # Could fail if a file is locked, etc. Silently skip.
                continue
        return deleted_sessions


    def get_session_path(self):
        return self.session_path
        
    def _validate_session_id(self, session_id):
        """Check if a given session ID corresponds to a real directory."""
        path_to_check = os.path.join(self.config['sessions_directory'], session_id)
        return os.path.isdir(path_to_check)

    def rename_session(self, label):
        """Renames the current session directory and log file to include a label."""
        # 1. Sanitize the label: allow letters, numbers, underscore, hyphen. Replace spaces with underscores.
        sanitized_label = re.sub(r'[^\w\s-]', '', label).strip()
        sanitized_label = re.sub(r'[-\s]+', '_', sanitized_label)
        if not sanitized_label:
            return False, "Invalid label. Please use letters, numbers, spaces, or hyphens."

        # 2. Construct the new name, removing any previous label to prevent stacking.
        base_id_parts = self.session_id.split('_')
        base_id = f"{base_id_parts[0]}_{base_id_parts[1]}_{base_id_parts[2]}"
        new_session_id = f"{base_id}_{sanitized_label}"

        # 3. Define old and new paths.
        old_path = self.session_path
        new_path = os.path.join(self.config['sessions_directory'], new_session_id)

        # 4. Check for conflicts.
        if os.path.exists(new_path):
            return False, f"A session named '{new_session_id}' already exists."

        try:
            # 5. Rename the main session directory first.
            os.rename(old_path, new_path)

            # 6. Now rename the log file inside the newly named directory.
            old_log_file = os.path.join(new_path, f"log_{self.session_id}.txt")
            new_log_file = os.path.join(new_path, f"log_{new_session_id}.txt")
            if os.path.exists(old_log_file):
                os.rename(old_log_file, new_log_file)

        except OSError as e:
            # Attempt to roll back the directory rename if it failed after.
            if os.path.exists(new_path) and not os.path.exists(old_path):
                os.rename(new_path, old_path)
            return False, f"Could not rename session due to a file system error: {e}"

        # 7. Update the instance's state to reflect the change.
        self.session_id = new_session_id
        self.session_path = new_path
        
        # 8. Update the master log to use the new file name.
        self.update_master_log()

        return True, f"Session renamed to '{new_session_id}'"


    def save_exchange(self, prompt, response):
        prompt_path = os.path.join(self.session_path, f"prompt_{self.next_seq_id}.txt")
        response_path = os.path.join(self.session_path, f"response_{self.next_seq_id}.txt")
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        with open(response_path, "w", encoding="utf-8") as f:
            f.write(response)
        current_id = self.next_seq_id
        self.next_seq_id += 1
        self.update_master_log()
        return current_id

    def delete_exchange(self, seq_id):
        prompt_path = os.path.join(self.session_path, f"prompt_{seq_id}.txt")
        response_path = os.path.join(self.session_path, f"response_{seq_id}.txt")
        deleted = False
        if os.path.exists(prompt_path):
            os.remove(prompt_path); deleted = True
        if os.path.exists(response_path):
            os.remove(response_path); deleted = True
        if deleted:
            self.update_master_log()
        return deleted
    
    def clear_session(self):
        """Deletes all exchange files in the current session and resets state."""
        try:
            for filename in os.listdir(self.session_path):
                file_path = os.path.join(self.session_path, filename)
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            self.next_seq_id = 1
            self.update_master_log()
            return True
        except Exception:
            return False

    def _get_sorted_exchange_ids(self):
        """Helper to get a sorted list of active exchange IDs."""
        ids = set()
        if not os.path.exists(self.session_path):
            return []
        for f in os.listdir(self.session_path):
            if f.startswith("prompt_") and f.endswith(".txt"):
                try:
                    ids.add(int(f.split('_')[1].split('.')[0]))
                except (ValueError, IndexError):
                    continue
        return sorted(list(ids))
        
    def delete_session(self, session_id):
        """Deletes an entire session folder."""
        if not self._validate_session_id(session_id):
            return False, "Session ID not found or is invalid."
        
        if session_id == self.session_id:
            return False, "Cannot delete the currently active session. Use /renew first."
            
        try:
            path_to_delete = os.path.join(self.config['sessions_directory'], session_id)
            shutil.rmtree(path_to_delete)
            return True, f"Successfully deleted session: {session_id}"
        except OSError as e:
            return False, f"Error deleting session directory: {e}"


    def load_full_history_string(self):
        """Loads and concatenates history into a single string (for Ollama)."""
        history = ""
        for seq_id in self._get_sorted_exchange_ids():
            prompt_path = os.path.join(self.session_path, f"prompt_{seq_id}.txt")
            response_path = os.path.join(self.session_path, f"response_{seq_id}.txt")
            if os.path.exists(prompt_path) and os.path.exists(response_path):
                with open(prompt_path, "r", encoding="utf-8") as f:
                    history += f"USER: {f.read()}\n\n"
                with open(response_path, "r", encoding="utf-8") as f:
                    history += f"ASSISTANT: {f.read()}\n\n"
        return history

    def load_structured_history(self):
        """Loads history into a structured list of messages (for OpenAI)."""
        messages = []
        for seq_id in self._get_sorted_exchange_ids():
            prompt_path = os.path.join(self.session_path, f"prompt_{seq_id}.txt")
            response_path = os.path.join(self.session_path, f"response_{seq_id}.txt")
            if os.path.exists(prompt_path) and os.path.exists(response_path):
                with open(prompt_path, "r", encoding="utf-8") as f:
                    messages.append({"role": "user", "content": f.read()})
                with open(response_path, "r", encoding="utf-8") as f:
                    messages.append({"role": "assistant", "content": f.read()})
        return messages

    def get_history_for_display(self):
        exchanges = []
        for seq_id in self._get_sorted_exchange_ids():
            prompt_path = os.path.join(self.session_path, f"prompt_{seq_id}.txt")
            response_path = os.path.join(self.session_path, f"response_{seq_id}.txt")
            prompt_content = ""
            response_content = ""
            if os.path.exists(prompt_path):
                with open(prompt_path, "r", encoding="utf-8") as f_p:
                    prompt_content = f_p.read()
            if os.path.exists(response_path):
                with open(response_path, "r", encoding="utf-8") as f_r:
                    response_content = f_r.read()
            if prompt_content or response_content:
                 exchanges.append({'id': seq_id, 'prompt': prompt_content, 'response': response_content})
        return exchanges


    def update_master_log(self):
        log_path = os.path.join(self.session_path, f"log_{self.session_id}.txt")
        history_for_log = ""
        exchanges = self.get_history_for_display()
        for ex in exchanges:
            history_for_log += f"--- Prompt {ex['id']} ---\n{ex['prompt']}\n\n"
            history_for_log += f"--- Response {ex['id']} ---\n{ex['response']}\n\n"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(history_for_log)

    def get_static_prompts(self):
        prompt_dir = self.config['static_prompts_directory']
        if not os.path.isdir(prompt_dir): return []
        return sorted([f for f in os.listdir(prompt_dir) if f.endswith(".txt")])

    def load_static_prompt(self, prompt_id):
        prompts = self.get_static_prompts()
        if 0 <= prompt_id < len(prompts):
            file_path = os.path.join(self.config['static_prompts_directory'], prompts[prompt_id])
            with open(file_path, "r", encoding="utf-8") as f: return f.read()
        return None

    def edit_prompt(self, seq_id, new_prompt_content):
        prompt_path = os.path.join(self.session_path, f"prompt_{seq_id}.txt")
        if not os.path.exists(prompt_path): return False
        with open(prompt_path, "w", encoding="utf-8") as f: f.write(new_prompt_content)
        return True
    
    def update_response_file(self, seq_id, response_content):
        response_path = os.path.join(self.session_path, f"response_{seq_id}.txt")
        with open(response_path, "w", encoding="utf-8") as f:
            f.write(response_content)
        self.update_master_log()

    def get_prompt_content(self, seq_id):
        prompt_path = os.path.join(self.session_path, f"prompt_{seq_id}.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f: return f.read()
        return None

    def save_specific_response(self, seq_id):
        response_path = os.path.join(self.session_path, f"response_{seq_id}.txt")
        if not os.path.exists(response_path): return None
        with open(response_path, "r", encoding="utf-8") as f: content = f.read()
        save_filename = f"{self.session_id}_response_{seq_id}.txt"
        save_path = os.path.join(self.config['saved_responses_directory'], save_filename)
        with open(save_path, "w", encoding="utf-8") as f: f.write(content)
        return save_path

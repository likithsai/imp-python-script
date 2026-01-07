#!/usr/bin/env python3
import os
import sys
import shlex
import getpass
import pickle
import io
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITERATIONS = 480000

class VaultError(Exception):
    pass

class PortableVault:
    def __init__(self, vault_file: Path, password: str):
        self.vault_file = vault_file
        self.staging_area = [] # List of Paths
        try:
            with open(self.vault_file, "rb") as f:
                self.container = pickle.load(f)
        except Exception:
            raise VaultError(f"Could not read vault file '{vault_file.name}'.")
        
        self.salt = self.container['salt']
        self.key = self._derive_key(password, self.salt)
        self.aesgcm = AESGCM(self.key)
        self._verify_vault()

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
        return kdf.derive(password.encode())

    def _verify_vault(self):
        try:
            self.aesgcm.decrypt(self.container['ver_nonce'], self.container['ver_tag'], None)
        except Exception:
            raise VaultError("Authentication failed: Incorrect password.")

    def _save(self):
        temp_file = self.vault_file.with_suffix(".tmp")
        with open(temp_file, "wb") as f:
            pickle.dump(self.container, f)
        temp_file.replace(self.vault_file)

    def stage_path(self, target_path: Path):
        if not target_path.exists():
            raise VaultError(f"Path '{target_path}' not found.")
        self.staging_area.append(target_path)

    def commit_updates(self):
        if not self.staging_area:
            print("∅ Nothing staged.")
            return
        
        for path in self.staging_area:
            if path.is_dir():
                # Process every file in folder tree individually
                for root, _, files in os.walk(path):
                    for file in files:
                        full_path = Path(root) / file
                        # Store using relative path from the parent of the added folder
                        rel_path = str(full_path.relative_to(path.parent))
                        self._encrypt_and_store(full_path, rel_path)
            else:
                self._encrypt_and_store(path, path.name)
            
        self._save()
        self.staging_area.clear()
        print("✔ Vault updated.")

    def _encrypt_and_store(self, disk_path: Path, vault_key: str):
        print(f" locking   ➔ {vault_key}", end="\r")
        data = disk_path.read_bytes()
        nonce = os.urandom(12)
        self.container['files'][vault_key] = (nonce, self.aesgcm.encrypt(nonce, data, None))
        self.container['metadata'][vault_key] = {'size': len(data)}

    def extract(self, vault_pattern: str, out_dir: Path):
        """Extracts a specific file or all files starting with a folder prefix."""
        out_dir.mkdir(parents=True, exist_ok=True)
        found = False
        
        for v_path in list(self.container['files'].keys()):
            # Match exact file OR files inside a folder prefix
            if v_path == vault_pattern or v_path.startswith(f"{vault_pattern}/"):
                found = True
                nonce, ciphertext = self.container['files'][v_path]
                data = self.aesgcm.decrypt(nonce, ciphertext, None)
                
                target = out_dir / v_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                print(f" extracted ➔ {v_path}")
        
        if not found:
            raise VaultError(f"No matches found for '{vault_pattern}'.")

    def delete(self, vault_pattern: str):
        # Unstage if present
        self.staging_area = [p for p in self.staging_area if p.name != vault_pattern]
        
        # Delete from container
        targets = [k for k in self.container['files'].keys() 
                   if k == vault_pattern or k.startswith(f"{vault_pattern}/")]
        
        if not targets:
            raise VaultError(f"'{vault_pattern}' not found.")
        
        for t in targets:
            del self.container['files'][t]
            del self.container['metadata'][t]
            print(f" removed   ✔ {t}")
        self._save()

def format_size(num):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(num) < 1024.0: return f"{num:3.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"

def run_shell(vault):
    while True:
        try:
            cmd_line = input(f"\033[1;32m{vault.vault_file.name}>\033[0m ").strip()
            if not cmd_line: continue
            parts = shlex.split(cmd_line)
            command, args = parts[0].lower(), parts[1:]

            match command:
                case "ls":
                    items = sorted(vault.container['files'].keys())
                    if not items and not vault.staging_area:
                        print("(empty)")
                    else:
                        for name in items:
                            size = vault.container['metadata'][name]['size']
                            print(f"{name} ({format_size(size)})")
                        for p in vault.staging_area:
                            print(f"(+) {p.name} (staged path)")

                case "add":
                    if not args: raise VaultError("Usage: add <path>")
                    vault.stage_path(Path(args[0]).expanduser())
                    print(f"✚ {args[0]} staged")

                case "update":
                    vault.commit_updates()

                case "extract":
                    if len(args) < 2: raise VaultError("Usage: extract <name> <dest_folder>")
                    vault.extract(args[0], Path(args[1]).expanduser())

                case "delete" | "rm":
                    if not args: raise VaultError("Usage: delete <name>")
                    vault.delete(args[0])

                case "exit" | "quit":
                    break

                case _:
                    print(f"Unknown command: {command}")

        except Exception as e:
            print(f"\033[31m❌ {e}\033[0m")

def main():
    try:
        if len(sys.argv) < 2:
            print("Usage: python vault.py <create/open> [name]")
            return
        
        if sys.argv[1] == "create":
            v_path = Path(sys.argv[2] if len(sys.argv) > 2 else "vault.vlt")
            pwd = getpass.getpass("New Password: ")
            if pwd != getpass.getpass("Confirm: "): return print("❌ Mismatch.")
            salt = os.urandom(16)
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
            key, nonce = kdf.derive(pwd.encode()), os.urandom(12)
            tag = AESGCM(key).encrypt(nonce, b"verify", None)
            with open(v_path, "wb") as f:
                pickle.dump({'salt': salt, 'ver_nonce': nonce, 'ver_tag': tag, 'files': {}, 'metadata': {}}, f)
            print(f"✨ Created {v_path.name}")
        else:
            v_path = Path(sys.argv[1])
            vault = PortableVault(v_path, getpass.getpass(f"🔑 Password for {v_path.name}: "))
            run_shell(vault)
    except KeyboardInterrupt: print("\n👋 Goodbye")
    except Exception as e: print(f"\033[31m❌ {e}\033[0m")

if __name__ == "__main__":
    main()
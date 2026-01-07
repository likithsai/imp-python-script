#!/usr/bin/env python3
import os, sys, shlex, getpass, pickle, hashlib, zlib
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITERATIONS = 480000

class VaultError(Exception): pass

class PortableVault:
    def __init__(self, vault_file: Path, password: str):
        self.vault_file, self.staging_area = vault_file, []
        try:
            with open(self.vault_file, "rb") as f: self.container = pickle.load(f)
        except: raise VaultError(f"Vault '{vault_file.name}' not found or corrupted.")
        
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=self.container['salt'], iterations=ITERATIONS)
        self.aesgcm = AESGCM(kdf.derive(password.encode()))
        try:
            self.aesgcm.decrypt(self.container['ver_nonce'], self.container['ver_tag'], None)
        except: raise VaultError("Incorrect password.")

    def _save(self):
        temp = self.vault_file.with_suffix(".tmp")
        with open(temp, "wb") as f: pickle.dump(self.container, f)
        temp.replace(self.vault_file)

    def commit(self):
        if not self.staging_area: return print("∅ Nothing staged.")
        for path in self.staging_area:
            base = path.parent
            files = [path] if path.is_file() else path.rglob('*')
            for p in files:
                if p.is_file():
                    print(f" packing ➔ {p.relative_to(base)}", end="\r")
                    raw = p.read_bytes()
                    comp = zlib.compress(raw, 6)
                    nonce = os.urandom(12)
                    self.container['files'][str(p.relative_to(base))] = (nonce, self.aesgcm.encrypt(nonce, comp, None))
                    self.container['metadata'][str(p.relative_to(base))] = {'orig': len(raw), 'comp': len(comp), 'hash': hashlib.sha256(raw).hexdigest()}
        self._save()
        self.staging_area.clear()
        print("✔ Vault updated.")

    def extract(self, pattern: str, out_dir: Path):
        out_dir.mkdir(parents=True, exist_ok=True)
        matches = [k for k in self.container['files'] if pattern in ("*", "all") or k == pattern or k.startswith(f"{pattern}/")]
        if not matches: raise VaultError(f"No match for '{pattern}'.")
        for k in matches:
            nonce, ctx = self.container['files'][k]
            raw = zlib.decompress(self.aesgcm.decrypt(nonce, ctx, None))
            if hashlib.sha256(raw).hexdigest() != self.container['metadata'][k]['hash']:
                print(f"⚠️ Corruption in {k}"); continue
            target = out_dir / k
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            print(f" extracted ➔ {k}")

    def delete(self, pattern: str):
        targets = [k for k in self.container['files'] if k == pattern or k.startswith(f"{pattern}/")]
        if not targets: raise VaultError(f"No match for '{pattern}'.")
        for t in targets:
            del self.container['files'][t], self.container['metadata'][t]
            print(f" removed ✔ {t}")
        self._save()

def shred(path: Path):
    if not path.is_file(): return
    size = path.stat().st_size
    with open(path, "ba+", buffering=0) as f:
        for _ in range(3): f.seek(0); f.write(os.urandom(size))
    path.unlink()

def fmt(n):
    for u in ['B','KB','MB','GB']:
        if abs(n) < 1024: return f"{n:3.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"

def run_shell(v):
    while True:
        try:
            cmd, *args = shlex.split(input(f"\033[1;32m{v.vault_file.name}>\033[0m ").strip())
            match cmd.lower():
                case "ls":
                    for k in sorted(v.container['files']): print(f"{k} ({fmt(v.container['metadata'][k]['orig'])})")
                    for p in v.staging_area: print(f"(+) {p.name}")
                    if not v.container['files'] and not v.staging_area: print("(empty)")
                case "add": v.staging_area.append(Path(args[0]).expanduser()); print(f"✚ Staged {args[0]}")
                case "update": v.commit()
                case "extract": v.extract(args[0], Path(args[1]) if len(args)>1 else Path("."))
                case "rm": v.delete(args[0])
                case "shred": 
                    if input(f"Shred {args[0]}? (y/n): ").lower()=='y': shred(Path(args[0])); print("🔥 Done")
                case "status":
                    o = sum(m['orig'] for m in v.container['metadata'].values())
                    c = sum(m['comp'] for m in v.container['metadata'].values())
                    print(f"Files: {len(v.container['files'])}\nRatio: {(1-c/o)*100:.1f}% saved" if o else "Empty")
                case "help": print("ls, add, update, extract, rm, shred, status, exit")
                case "exit": break
        except EOFError: break
        except Exception as e: print(f"\033[31m❌ {e}\033[0m")

def main():
    if len(sys.argv) < 2: return print("Usage: python vault.py <create/open> [name]")
    v_path = Path(sys.argv[2] if len(sys.argv) > 2 else sys.argv[1])
    if sys.argv[1] == "create":
        p = getpass.getpass("Password: ")
        if p != getpass.getpass("Confirm: "): return print("❌ Mismatch")
        salt, nonce = os.urandom(16), os.urandom(12)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
        tag = AESGCM(kdf.derive(p.encode())).encrypt(nonce, b"v", None)
        with open(v_path, "wb") as f: pickle.dump({'salt':salt, 'ver_nonce':nonce, 'ver_tag':tag, 'files':{}, 'metadata':{}}, f)
        print(f"✨ Created {v_path.name}")
    else:
        v = PortableVault(v_path, getpass.getpass(f"🔑 Password: "))
        run_shell(v)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\n👋 Goodbye")
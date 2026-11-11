"""Create local synthetic configuration without printing credentials or overwriting local choices."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
target = root / '.env'
if target.exists():
    print('Existing .env retained.')
else:
    text = (root / '.env.example').read_text().replace(
        'local-synthetic-only-replace-before-use', secrets.token_hex(32))
    with open(target, 'x', opener=lambda path, flags: __import__('os').open(path, flags, 0o600)) as stream:
        stream.write(text)
    print('Created private local .env with a random synthetic identity key.')

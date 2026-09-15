import json
from pathlib import Path

chunks = json.loads(Path('data/chunks.json').read_text())
print(f'Total chunks: {len(chunks)}\n')
for chunk in chunks:
    print(f'ID {chunk["id"]}: {chunk["title"]} ({len(chunk["text"])} chars)')

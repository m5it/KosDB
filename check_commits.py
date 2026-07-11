import subprocess
import sys

commits = ['e25db99', 'c59b686', 'd384101', '4d2aad0', '8e234ac']
for c in commits:
    try:
        result = subprocess.run(
            ['git', 'show', f'{c}:commands.py'],
            capture_output=True, text=True
        )
        lines = result.stdout.count('\n')
        chars = len(result.stdout)
        print(f'{c}: {lines} lines, {chars} chars')
    except Exception as e:
        print(f'{c}: error {e}')

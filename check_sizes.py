import subprocess
commits = [
    'e25db99',  # v3.4.0
    'c59b686',  # v3.3.0
    'd384101',  # v3.2.0
    '4d2aad0',  # v3.1.0
]
for c in commits:
    try:
        size = subprocess.check_output(['git', 'show', f'{c}:commands.py'], text=True)
        lines = size.splitlines()
        print(f"{c}: {len(size)} chars, {len(lines)} lines")
    except Exception as e:
        print(f"{c}: ERROR - {e}")

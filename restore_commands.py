import subprocess

# Get clean commands.py from git HEAD
result = subprocess.run(
    ['git', 'show', 'HEAD:commands.py'],
    capture_output=True,
    text=True
)

if result.returncode != 0:
    print("ERROR:", result.stderr)
    exit(1)

with open('commands.py', 'w') as f:
    f.write(result.stdout)

print(f"Restored commands.py: {len(result.stdout)} chars, {result.stdout.count(chr(10))} lines")

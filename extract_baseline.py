import subprocess

# Extract clean v3.3.0 commands.py baseline
result = subprocess.run(
    ['git', 'show', 'c59b686:commands.py'],
    capture_output=True, text=True, check=True
)

with open('commands_baseline.py', 'w') as f:
    f.write(result.stdout)

print(f"Extracted baseline: {len(result.stdout)} chars, {len(result.stdout.splitlines())} lines")

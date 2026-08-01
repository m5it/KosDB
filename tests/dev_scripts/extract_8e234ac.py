import subprocess
with open('commands_8e234ac.py', 'w') as f:
    r = subprocess.run(['git', 'show', '8e234ac:commands.py'], capture_output=True, text=True)
    f.write(r.stdout)
print(len(r.stdout), 'chars', len(r.stdout.splitlines()), 'lines')

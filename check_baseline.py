import subprocess
for commit in ['c59b686', 'd384101', '4d2aad0', '8e234ac']:
    try:
        data = subprocess.check_output(['git', 'show', f'{commit}:commands.py'], text=True)
        # Count occurrences of class definition and handlers dict
        class_count = data.count('class CommandRegistry')
        handlers_count = data.count("self.handlers = {")
        lines = data.count('\n')
        print(f"{commit}: {len(data)} chars, {lines} lines, {class_count} classes, {handlers_count} handlers_dicts")
        # Try compile
        try:
            compile(data, f'commands_{commit}.py', 'exec')
            print(f"  -> COMPILES OK")
        except SyntaxError as e:
            print(f"  -> SYNTAX ERROR: {e}")
    except Exception as e:
        print(f"{commit}: ERROR {e}")

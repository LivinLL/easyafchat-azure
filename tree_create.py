import os

def generate_tree(startpath, output_file, exclude_dirs=None, max_depth=10):
    if exclude_dirs is None:
        exclude_dirs = ['venv', '.git', '__pycache__', '.pytest_cache', 'node_modules']
    
    # Ensure startpath is an absolute path to prevent any potential path manipulation
    startpath = os.path.abspath(startpath)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for root, dirs, files in os.walk(startpath):
            # Calculate the directory depth
            level = root.replace(startpath, '').count(os.sep)
            
            # Limit directory depth
            if level > max_depth:
                del dirs[:]
                continue
            
            # Remove excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            indent = ' ' * 4 * level
            
            # Print directory name
            subpath = os.path.relpath(root, startpath)
            if subpath != '.':
                f.write(f'{indent}{os.path.basename(root)}/\n')
            
            # Print files
            subindent = indent + '    '
            for file in files:
                f.write(f'{subindent}{file}\n')

# Use the function
generate_tree('.', 'tree_structure.txt')

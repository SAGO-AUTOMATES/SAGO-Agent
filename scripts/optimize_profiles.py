#!/usr/bin/env python3
"""Optimize agent profiles by removing redundant information."""

import os
import re
from pathlib import Path


def optimize_system_prompt(prompt: str) -> str:
    """Optimize a system prompt by removing redundant information."""
    if not prompt:
        return prompt
    
    lines = prompt.split('\n')
    optimized_lines = []
    skip_next_separator = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Skip empty lines followed by separators
        if stripped == '' and i + 1 < len(lines) and lines[i + 1].strip() == '---':
            i += 2
            continue
        
        # Skip standalone separators
        if stripped == '---':
            i += 1
            continue
        
        # Skip personality matrix tables
        if '### Personality Matrix' in stripped:
            # Skip until we hit the next section or separator
            i += 1
            while i < len(lines):
                if lines[i].strip().startswith('##') or lines[i].strip().startswith('###') or lines[i].strip() == '---':
                    break
                i += 1
            continue
        
        # Skip duplicate headers (keep numbered version)
        if stripped.startswith('## ') and i > 0:
            # Check if previous non-empty line is a duplicate header
            prev_idx = i - 1
            while prev_idx >= 0 and lines[prev_idx].strip() == '':
                prev_idx -= 1
            
            if prev_idx >= 0:
                prev_line = lines[prev_idx].strip()
                # Skip if it's a duplicate like "### Identity & Persona" followed by "## 1. Identity & Persona"
                if (prev_line.startswith('### ') and 
                    stripped.startswith('## ') and 
                    any(c.isdigit() for c in stripped)):
                    i += 1
                    continue
        
        # Skip verbose "Name:" and "Codename:" lines
        if stripped.startswith('**Name:**') or stripped.startswith('**Codename:**'):
            i += 1
            continue
        
        # Keep the line
        optimized_lines.append(line)
        i += 1
    
    # Remove consecutive empty lines (keep max 1)
    result = []
    prev_empty = False
    for line in optimized_lines:
        is_empty = line.strip() == ''
        if is_empty and prev_empty:
            continue
        result.append(line)
        prev_empty = is_empty
    
    return '\n'.join(result).strip()


def optimize_agent_profile(filepath: Path) -> bool:
    """Optimize a single agent profile file."""
    content = filepath.read_text()
    
    # Extract the system_prompt string
    match = re.search(r'system_prompt="""(.*?)"""', content, re.DOTALL)
    if not match:
        return False
    
    original_prompt = match.group(1)
    optimized_prompt = optimize_system_prompt(original_prompt)
    
    if len(optimized_prompt) >= len(original_prompt):
        return False  # No improvement
    
    # Replace in content
    new_content = content.replace(
        f'system_prompt="""{original_prompt}"""',
        f'system_prompt="""{optimized_prompt}"""'
    )
    
    filepath.write_text(new_content)
    return True


def main():
    profiles_dir = Path('sago/agents/profiles')
    
    if not profiles_dir.exists():
        print(f"Error: {profiles_dir} not found")
        return
    
    optimized_count = 0
    total_original_lines = 0
    total_optimized_lines = 0
    
    for filepath in sorted(profiles_dir.glob('*.py')):
        if filepath.name == '__init__.py':
            continue
        
        # Count original lines
        content = filepath.read_text()
        match = re.search(r'system_prompt="""(.*?)"""', content, re.DOTALL)
        if not match:
            continue
            
        original_lines = len(match.group(1).split('\n'))
        total_original_lines += original_lines
        
        if optimize_agent_profile(filepath):
            optimized_count += 1
            # Count optimized lines
            content = filepath.read_text()
            match = re.search(r'system_prompt="""(.*?)"""', content, re.DOTALL)
            if match:
                optimized_lines = len(match.group(1).split('\n'))
                total_optimized_lines += optimized_lines
                print(f"✓ {filepath.name}: {original_lines} → {optimized_lines} lines")
        else:
            # Still count for totals
            total_optimized_lines += original_lines
    
    print(f"\n{'='*60}")
    print(f"Optimized {optimized_count} profiles")
    print(f"Total lines: {total_original_lines} → {total_optimized_lines}")
    print(f"Saved {total_original_lines - total_optimized_lines} lines ({((total_original_lines - total_optimized_lines) / total_original_lines * 100):.1f}%)")


if __name__ == '__main__':
    main()

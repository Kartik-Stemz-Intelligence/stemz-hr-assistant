from docx import Document
from pathlib import Path

doc = Document('knowledge/new-knowledge/HR Playbook - 09092026.docx')

# Extract all paragraphs
all_paras = []
for para in doc.paragraphs:
    text = para.text.strip()
    if text and not text.startswith('●●●') and '━━' not in text:
        all_paras.append(text)

# Known section headers to detect
major_sections = {
    'AttendanceRules': 'Attendance Rules',
    'WorkingHours': 'Working Hours',
    'Flexi': 'Flexi Working Hours',
    'Dress Code': 'Dress Code',
    "Men's Dress Code": "Men's Dress Code",
    "Women's Dress Code": "Women's Dress Code",
    'POSH': 'Prevention of Sexual Harassment',
    'WhatConstitutes SexualHarassment': 'What Constitutes Sexual Harassment',
    'Reporting & Investigation': 'Reporting & Investigation',
    'CentralICC Members': 'Central ICC Members',
    'Local ICC Members': 'Local ICC Members',
    'Anti-Harassment': 'Anti-Harassment',
    'Whistle Blower Policy': 'Whistle Blower Policy',
    'Disciplinary Action': 'Disciplinary Action',
    'Employee Misconduct': 'Employee Misconduct',
    'RespectingDiversity': 'Respecting Diversity & Inclusion',
    'Gender Sensitivity': 'Gender Sensitivity',
    'ID/Access Cards': 'ID/Access Cards & QMC Visits',
    'Key Leave Rules': 'Key Leave Rules',
    'Leave Types': 'Leave Types',
    'Insurance': 'Insurance Benefits',
    'Travel': 'Travel & Relocation',
    'Probation': 'Probation, Confirmation & Termination',
    'Performance': 'Performance Review & Rewards',
}

markdown = []
markdown.append('---')
markdown.append('title: STEMZ Healthcare HR Playbook')
markdown.append('document: STEMZ Healthcare HR Playbook')
markdown.append('category: HR Policies')
markdown.append('version: 1')
markdown.append('effective_date: 2026-09-09')
markdown.append('status: active')
markdown.append('---\n')

skip_patterns = [
    'TABLE OF CONTENTS', 'For Internal Use', 'STEMZ HEALTHCARE | HR PLAYBOOK',
    'Your Complete Guide', 'Human Resources Department', 'Confidential', 'Page '
]

current_section = None
for para in all_paras:
    # Skip header/footer lines
    if any(skip in para for skip in skip_patterns):
        continue
    
    # Detect section headers (short lines that are likely headers)
    is_header = False
    for key, display_name in major_sections.items():
        if key in para and len(para) < 80:
            markdown.append(f'\n## {display_name}\n')
            current_section = para
            is_header = True
            break
    
    if not is_header and para and len(para) > 0:
        # Add bullet point formatting for list items
        if para.startswith('●') or (para and not para[0].isalpha() and para[1:].lstrip().startswith(('a', 'b', 'c'))):
            markdown.append(f'- {para.lstrip("● ")}')
        else:
            markdown.append(para)

# Write output
output = Path('knowledge/new-knowledge/HR-Playbook.md')
output.write_text('\n'.join(markdown), encoding='utf-8')
print(f'✅ Converted to Markdown: {output}')
print(f'Total content lines: {len(markdown)}')

# Show preview
print('\nFirst 50 lines:')
for i, line in enumerate(markdown[:50]):
    print(f'{i}: {line[:80]}')

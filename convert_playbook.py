from docx import Document
from pathlib import Path

doc_path = Path('knowledge/new-knowledge/HR Playbook - 09092026.docx')
doc = Document(str(doc_path))

# Extract all paragraphs and clean up
lines = []
for para in doc.paragraphs:
    text = para.text.strip()
    if text and not text.startswith('●●●'):  # Skip decorative lines
        lines.append(text)

# Section keywords to identify headers
section_keywords = [
    'Attendance', 'Corporate Dress Code', 'Prevention of Sexual Harassment',
    'Anti-Harassment', 'Disciplinary Action', 'Diversity', 'Gender Sensitivity',
    'ID/Access Cards', 'QMC Visits', 'Leaves', 'Holidays', 'Insurance',
    'Travel Reimbursement', 'Relocation', 'Probation', 'Confirmation',
    'Termination', 'Performance Review', 'Rewards', 'Attendance Process',
    'Overtime', 'TOIL', 'Courier', 'Mobile Phone', 'Uniform', 'Locker',
    'Reimbursement Guidelines', 'Working Hours', 'WFH', 'Leave', 'OD',
    'Salary', 'Shift', 'Policy', 'Flexitime', 'Rules', 'Hours', 'Process'
]

markdown_output = []
markdown_output.append('---')
markdown_output.append('title: STEMZ Healthcare HR Playbook')
markdown_output.append('document: STEMZ Healthcare HR Playbook')
markdown_output.append('category: HR Policies')
markdown_output.append('version: 1')
markdown_output.append('effective_date: 2026-09-09')
markdown_output.append('status: active')
markdown_output.append('---')
markdown_output.append('')

# Skip lines to find actual content
skip_count = 0
for i, line in enumerate(lines):
    # Skip TOC and headers
    if any(skip in line for skip in ['TABLE OF CONTENTS', 'For Internal Use', 'STEMZ HEALTHCARE | HR PLAYBOOK', 'Your Complete Guide', 'Human Resources Department', 'Confidential']):
        skip_count = i + 15
        continue
    
    if i < skip_count:
        continue
    
    # Detect section headers
    is_section = (
        len(line) < 60 and 
        (any(kw in line for kw in section_keywords) or line.isupper())
    )
    
    if is_section and len(line) > 3 and not line.startswith('Page'):
        markdown_output.append(f'\n## {line}\n')
    elif line and not line.startswith('Page'):
        markdown_output.append(line)

# Write to Markdown file
output_path = Path('knowledge/new-knowledge/HR-Playbook.md')
output_path.write_text('\n'.join(markdown_output), encoding='utf-8')
print(f'✅ Converted to Markdown: {output_path}')
print(f'Total lines: {len(markdown_output)}')

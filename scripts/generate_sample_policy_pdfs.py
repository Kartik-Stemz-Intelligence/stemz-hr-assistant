from pathlib import Path
import textwrap

import fitz


KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / 'knowledge' / 'pdf-knowledge'


def _build_doc_text(meta: dict[str, str], sections: list[tuple[str, str]]) -> str:
    lines = ['---']
    for key, value in meta.items():
        lines.append(f'{key}: {value}')
    lines.append('---')
    lines.append('')
    for title, body in sections:
        lines.append(f'## {title}')
        lines.append(body)
        lines.append('')
    return '\n'.join(lines).strip() + '\n'


def _write_pdf(path: Path, content: str) -> None:
    doc = fitz.open()
    page_w, page_h = 595, 842  # A4 points
    left, top, right, bottom = 48, 48, 547, 794
    max_chars = 92
    line_h = 14

    lines = []
    for raw in content.splitlines():
        if not raw.strip():
            lines.append('')
            continue
        if raw.startswith('## '):
            lines.append(raw)
            continue
        wrapped = textwrap.wrap(raw, width=max_chars, replace_whitespace=False, drop_whitespace=False)
        lines.extend(wrapped or [''])

    page = doc.new_page(width=page_w, height=page_h)
    y = top
    for line in lines:
        if y > bottom:
            page = doc.new_page(width=page_w, height=page_h)
            y = top

        if line.startswith('## '):
            page.insert_text((left, y), line, fontsize=11.5, fontname='helv', fill=(0.1, 0.1, 0.1))
            y += int(line_h * 1.2)
            continue

        page.insert_text((left, y), line, fontsize=10.2, fontname='helv', fill=(0.18, 0.18, 0.18))
        y += line_h

    doc.save(path)
    doc.close()


def main() -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    docs = [
        {
            'filename': 'pdf-attendance-policy-v2.pdf',
            'meta': {
                'title': 'Attendance and Punctuality Policy',
                'document': 'Attendance and Punctuality Policy v2',
                'category': 'Attendance',
                'version': '2.0',
                'effective_date': '2026-08-01',
                'approved_by': 'People Operations',
                'status': 'active',
                'confidential': 'false',
                'source': 'HR Policy Manual',
            },
            'sections': [
                ('Scope and Purpose', 'This Attendance and Punctuality Policy establishes a uniform framework for office presence, shift adherence, and punctuality expectations across all business units. It applies to full-time employees, probationary employees, consultants assigned to internal teams, and fixed-term contract staff unless a written exception exists in an employment agreement. The purpose of this policy is to create fair and transparent attendance standards, enable reliable workforce planning, and reduce ambiguity in how attendance exceptions are reviewed by managers and HR.'),
                ('Work Hours and Presence Expectations', 'The standard office schedule is 9:00 AM to 6:00 PM with a designated meal break. Departments with approved operational shifts may follow alternate hours, provided those schedules are documented and communicated in advance. Employees are expected to be present and available during core collaboration windows defined by their department. Team meetings, customer commitments, and cross-functional handoffs should not be impacted by repeated delays in start times or unplanned absenteeism.'),
                ('Late Arrival Threshold and Documentation', 'Employees are allowed up to three late arrivals per calendar month as an operational buffer for commute delays and genuine disruptions. A late arrival is recorded when check-in occurs more than ten minutes after assigned start time. Once the monthly threshold is exceeded, the employee must provide a written explanation in the attendance system and discuss preventive actions with the reporting manager. Managers may request supporting context where required, including transport disruptions, medical contingencies, or temporary caregiving obligations.'),
                ('Unplanned Absence and Notification Timeline', 'If an employee cannot attend work on a given day, they must inform both their reporting manager and team coordinator as early as possible, and no later than one hour after scheduled start time unless exceptional circumstances prevent communication. Notification should include expected duration of absence, current work dependencies, and a handover note for urgent items. Repeated same-day absence notifications without clear reason may trigger HR advisory review to assess attendance reliability and support requirements.'),
                ('Escalation and Corrective Action', 'Attendance concerns are addressed progressively with an emphasis on coaching first. The first stage is manager feedback and expectation reset. The second stage is a documented improvement plan with measurable attendance targets over four to eight weeks. Continued non-adherence may result in formal disciplinary steps under the Code of Conduct framework. HR will ensure consistency across departments and prevent arbitrary enforcement by requiring objective attendance records and documented manager feedback.'),
                ('Data Integrity and Compliance', 'Attendance records generated by biometric, access-card, or approved workforce systems are considered the source of truth for payroll inputs and compliance reporting. Tampering with attendance records, proxy attendance, or intentional misrepresentation of check-in information is treated as a serious policy violation. Employees may raise a correction request for genuine system errors through HR operations within three working days, after which payroll-impacting corrections may require additional approval.'),
            ],
        },
        {
            'filename': 'pdf-leave-and-wfh-policy.pdf',
            'meta': {
                'title': 'Leave and WFH Guidelines',
                'document': 'Leave and Work From Home Guidelines',
                'category': 'Leave',
                'version': '1.4',
                'effective_date': '2026-06-15',
                'approved_by': 'HRBP',
                'status': 'active',
                'confidential': 'false',
                'source': 'HR Policy Manual',
            },
            'sections': [
                ('Policy Intent and Applicability', 'The Leave and Work From Home Guidelines define how employees can plan time away from work while maintaining continuity, service quality, and team coordination. The policy applies to all confirmed employees and role-eligible contract staff. It is designed to balance flexibility with operational accountability by requiring transparent planning, timely communication, and clear approval pathways for both planned leave and remote-work requests.'),
                ('WFH Eligibility and Monthly Allowance', 'Employees in roles that do not require mandatory on-site presence may request up to two work-from-home days per month. Approval is contingent on deliverables, team coverage, customer commitments, and prior attendance compliance. Managers retain discretion to decline requests when business-critical activities require in-person participation. Departments with seasonal peaks may publish temporary blackout windows during which WFH requests are restricted.'),
                ('Advance Notice and Emergency Exceptions', 'WFH requests should be submitted at least two working days in advance through the approved workflow tool. Emergency requests (for example acute medical events, dependent-care disruptions, or severe weather impact) can be submitted on short notice, but employees must notify the manager directly via call or official messaging channel. Emergency approvals are exception-based and reviewed periodically to prevent misuse patterns.'),
                ('Planned Leave Types and Approval Discipline', 'Planned leave includes casual leave, earned leave, and approved personal leave categories defined in employment terms. Employees should avoid clustering leave around critical project milestones without early planning. Manager approvals should be based on staffing balance, project risk, and fairness to peers. HR may intervene in cases where repeated leave rejections suggest inconsistent managerial practices or where policy interpretation differs across teams.'),
                ('Partial Day Rules and Combining Leave with WFH', 'Half-day leave and WFH on the same calendar day is generally discouraged because it creates ambiguity in availability windows and payroll coding. Such combinations require explicit manager approval and may require HR confirmation for payroll alignment. Employees are expected to maintain calendar transparency for all approved partial-day arrangements and ensure handoffs are completed for customer-facing responsibilities.'),
                ('Accountability, Monitoring, and Misuse Prevention', 'All approved leave and WFH requests are auditable and can be reviewed for trend analysis, coverage gaps, and policy consistency. Repeated last-minute requests without valid rationale, non-responsiveness during approved WFH hours, or pattern-based misuse may result in reduced flexibility privileges and formal advisory discussion. The objective is corrective guidance and reliable execution rather than punitive action, except in deliberate misuse cases.'),
            ],
        },
        {
            'filename': 'pdf-executive-compensation-confidential.pdf',
            'meta': {
                'title': 'Executive Compensation Framework',
                'document': 'Executive Compensation Framework FY27',
                'category': 'Compensation',
                'version': '1.0',
                'effective_date': '2026-07-01',
                'approved_by': 'Compensation Committee',
                'status': 'restricted',
                'confidential': 'true',
                'source': 'Board Approved Policy',
            },
            'sections': [
                ('Confidentiality Notice', 'This policy is designated confidential and restricted to authorized HR leadership, executive management, compensation committee members, and board-audited finance partners. The contents include strategic remuneration parameters, payout governance methodology, and high-impact decision criteria that are not intended for broad employee distribution. Unauthorized access, forwarding, reproduction, or disclosure of this document is prohibited and treated as a serious breach of confidentiality obligations.'),
                ('Framework Objectives and Governance', 'The Executive Compensation Framework aligns executive incentives with long-term enterprise value, responsible growth, governance maturity, and risk-managed performance outcomes. Compensation decisions are reviewed by the compensation committee, validated against approved budgets, and benchmarked using market-median and upper-quartile references for equivalent leadership responsibilities. Payout decisions must be traceable to defined business outcomes and documented in committee minutes for audit defensibility.'),
                ('Compensation Components', 'Executive compensation includes fixed annual base, performance-linked short-term incentives, strategic milestone incentives, retention-linked components, and deferred value mechanisms where applicable. Role criticality, succession risk, and sustained contribution are considered alongside annual performance ratings. Incentive curves are calibrated to avoid disproportionate payouts for short-term gains that introduce long-term operational or compliance risk.'),
                ('Bonus Multiplier Methodology', 'Annual bonus outcomes are determined through weighted performance pillars including financial discipline, growth quality, customer outcomes, compliance posture, leadership behavior, and organizational capability development. Each pillar has a threshold, target, and stretch band with defined multipliers. Committee-level discretion may adjust outcomes in exceptional cases such as extraordinary market disruption, regulatory directives, or major one-time strategic events, provided rationale is formally documented.'),
                ('Controls, Disclosure Limits, and Escalation', 'Access to individualized compensation data is provisioned on a strict need-to-know basis and monitored through controlled systems. Any request for disclosure outside approved governance channels must be escalated to legal and compliance before response. Internal discussions should avoid referencing named individual payout figures in unsecured channels. Potential leakage incidents are subject to immediate containment, digital forensics review, and corrective disciplinary action.'),
                ('Review Cadence and Auditability', 'The framework is reviewed at least annually and additionally when material business or regulatory changes occur. All revisions require formal approval and version control. Historical decisions, assumptions, and exception approvals are retained for governance audits. The policy is intended to ensure strategic alignment, fairness at executive levels, and clear accountability for compensation decisions with enterprise impact.'),
            ],
        },
        {
            'filename': 'pdf-investigation-protocol-confidential.pdf',
            'meta': {
                'title': 'Employee Investigation Protocol',
                'document': 'Internal Investigation Protocol',
                'category': 'Disciplinary',
                'version': '3.1',
                'effective_date': '2026-05-20',
                'approved_by': 'Legal and Compliance',
                'status': 'restricted',
                'confidential': 'true',
                'source': 'Compliance Office',
            },
            'sections': [
                ('Confidentiality Notice', 'This protocol is confidential and intended only for authorized HR, legal, compliance, and designated investigation stakeholders. Investigation records frequently contain sensitive personal data, reputationally significant information, and legally privileged communications. Unauthorized circulation or discussion of active cases can compromise fairness, expose the organization to legal risk, and breach privacy commitments. Strict confidentiality obligations apply throughout and after case closure.'),
                ('Guiding Principles and Fair Process', 'All investigations must follow principles of neutrality, proportionality, procedural fairness, and evidence-based evaluation. No conclusions should be formed before adequate fact collection and contextual review. Individuals subject to allegations must be given an opportunity to respond unless legal constraints require temporary confidentiality before notice. Investigators must avoid conflicts of interest and escalate assignment concerns immediately when independence could be questioned.'),
                ('Case Intake and Triage', 'Every complaint or allegation must be logged with timestamp, source channel, issue category, severity indicator, and immediate risk notes. Triage determines whether the matter is suitable for managerial resolution, HR fact-finding, or formal legal-compliance investigation. High-severity matters involving harassment, fraud, data misuse, retaliation, or safety issues require immediate escalation and interim risk controls to protect stakeholders while inquiry is ongoing.'),
                ('Evidence Handling and Chain of Custody', 'Investigation evidence may include email records, approved communication logs, system audit trails, access logs, CCTV extracts (where lawful), witness statements, and policy acknowledgements. Each evidence item must be tagged with source, acquisition date, handler identity, and integrity notes. Evidence repositories must enforce least-privilege access and maintain tamper-evident logs. Any gap in chain-of-custody documentation should be reported and remediated before decision-making.'),
                ('Interviews and Documentation Standards', 'Witness and subject interviews must be documented with factual neutrality, date/time records, and clear differentiation between direct statements and investigator observations. Leading questions and coercive framing are prohibited. Participants should be informed of confidentiality expectations and non-retaliation protections. Investigation notes must be retained in standardized templates so findings can be consistently reviewed by HR leadership and legal counsel.'),
                ('Findings, Outcome Communication, and Record Retention', 'Findings should classify allegations as substantiated, partially substantiated, unsubstantiated, or inconclusive based on available evidence quality. Recommended actions must be proportional and policy-aligned, including coaching, corrective action, process controls, or disciplinary measures. Outcome communication should balance transparency with privacy obligations. Closed-case records are retained according to retention schedules and legal hold requirements, with periodic access reviews for compliance.'),
            ],
        },
        {
            'filename': 'pdf-code-of-conduct-summary.pdf',
            'meta': {
                'title': 'Code of Conduct Summary',
                'document': 'Employee Code of Conduct Summary',
                'category': 'Conduct',
                'version': '2.2',
                'effective_date': '2026-04-10',
                'approved_by': 'HR Operations',
                'status': 'active',
                'confidential': 'false',
                'source': 'Employee Handbook',
            },
            'sections': [
                ('Purpose and Values Alignment', 'The Code of Conduct Summary outlines behavioral expectations that protect trust, collaboration, and accountability across the organization. It translates company values into practical daily standards applicable to all employees regardless of role or tenure. The code supports a safe and respectful workplace, ethical decision-making, and professional consistency in internal and external interactions. Every employee is expected to read, understand, and follow these standards as a condition of employment.'),
                ('Professional Behavior and Respectful Communication', 'Employees must maintain professional conduct in meetings, written communication, and informal interactions. Disrespectful language, intimidation, harassment, and discriminatory behavior are prohibited. Constructive disagreement is encouraged when expressed with factual reasoning and respect. Managers are expected to model communication hygiene, including timely feedback, clear expectations, and non-retaliatory conflict handling. Cross-functional collaboration should prioritize clarity, ownership, and mutual accountability.'),
                ('Conflict of Interest and Disclosure Expectations', 'Any personal, financial, or relational interest that could influence business decisions must be disclosed promptly to HR and the reporting manager. This includes vendor relationships, familial reporting lines, external consulting that overlaps with company operations, and gifts that may create undue influence. Early disclosure enables objective review and mitigation planning. Non-disclosure of material conflicts is treated as a conduct violation even if no adverse outcome is immediately visible.'),
                ('Data Protection, Security, and Responsible Use', 'Employees are custodians of company and customer information and must use approved systems, secure channels, and access controls. Sharing confidential data outside authorized boundaries, bypassing security controls, or using unapproved storage platforms is prohibited. Devices and accounts should be protected through strong authentication practices and timely reporting of suspicious activity. Information handling must align with privacy, legal, and contractual requirements applicable to each function.'),
                ('Reporting Concerns and Non-Retaliation', 'Employees are encouraged to report suspected misconduct, policy violations, or safety concerns through established channels, including HR and compliance contacts. Reports made in good faith are protected under non-retaliation expectations. Managers must handle concerns seriously, preserve confidentiality to the extent possible, and avoid actions that could discourage future reporting. Anonymous reporting options may be used where available, subject to investigation feasibility.'),
                ('Violation Management and Corrective Outcomes', 'Conduct concerns are reviewed based on severity, intent, recurrence, and impact. Outcomes may include coaching, written warning, role restriction, suspension, or termination depending on facts and policy context. Corrective action decisions should be consistent across comparable cases and supported by documentation. The objective is to protect workplace standards, prevent recurrence, and reinforce a culture of integrity and accountability.'),
            ],
        },
    ]

    for doc in docs:
        path = KNOWLEDGE_DIR / doc['filename']
        content = _build_doc_text(doc['meta'], doc['sections'])
        _write_pdf(path, content)
        print(f'Created: {path.name}')


if __name__ == '__main__':
    main()

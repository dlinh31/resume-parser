import json
import re
from datetime import datetime, timezone
from pathlib import Path

_SEASONAL = {
    'spring': '05',
    'summer': '08',
    'fall': '12',
    'autumn': '12',
    'winter': '01',
}

_LEGAL_SUFFIX_RE = re.compile(
    r'[\s,]*(&\s*)?\b(LLC|Inc|Corp|Ltd|L\.P\.|L\.L\.C\.|Co|LLP|PLC|GmbH|S\.A\.|B\.V\.)\b\.?\s*$',
    re.IGNORECASE,
)

_REMOTE_PARENS_RE = re.compile(r'\s*\(\s*remote\s*\)\s*$', re.IGNORECASE)
_REMOTE_SUFFIX_RE = re.compile(r',\s*remote\s*$', re.IGNORECASE)

_US_STATES = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
    'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
    'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID',
    'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
    'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
    'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
    'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV',
    'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
    'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK',
    'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
    'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT',
    'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV',
    'wisconsin': 'WI', 'wyoming': 'WY', 'district of columbia': 'DC',
}


def _load_skills_map() -> dict[str, str]:
    data_path = Path(__file__).parent.parent / 'data' / 'skills_map.json'
    with open(data_path) as f:
        return json.load(f)


_SKILLS_MAP: dict[str, str] = _load_skills_map()


def _parse_date_iso(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    if not s or s.lower() in ('present', 'current', 'now'):
        return None
    if '&' in s:
        return None
    s = re.sub(r'^expected\s+', '', s, flags=re.IGNORECASE).strip()
    m = re.match(r'^(spring|summer|fall|autumn|winter)\s+(\d{4})$', s, re.IGNORECASE)
    if m:
        return f"{m.group(2)}-{_SEASONAL[m.group(1).lower()]}"
    if '/' in s and re.search(r'[A-Za-z]', s):
        return None
    s = re.sub(r'\bSept\b', 'Sep', s, flags=re.IGNORECASE)
    s = re.sub(r'\b([A-Za-z]{3,9})\.', r'\1', s)
    m = re.match(r'^(\d{2})/(\d{4})$', s)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    if re.match(r'^\d{4}$', s):
        return s
    for fmt in ('%b %Y', '%B %Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m')
        except ValueError:
            pass
    return None


def _is_expected_date(raw: str | None) -> bool:
    if not raw:
        return False
    return bool(re.match(r'^expected\b', raw.strip(), re.IGNORECASE))


def _normalize_company(raw: str) -> str:
    return _LEGAL_SUFFIX_RE.sub('', raw).strip().rstrip(',').strip()


def _normalize_location(raw: str | None) -> tuple[str | None, bool]:
    if not raw:
        return None, False
    s = raw.strip()
    if s.lower() == 'remote':
        return None, True
    is_remote = False
    s, n = _REMOTE_PARENS_RE.subn('', s)
    if n:
        is_remote = True
    s, n = _REMOTE_SUFFIX_RE.subn('', s)
    if n:
        is_remote = True
    s = s.strip().rstrip(',').strip()
    parts = s.rsplit(',', 1)
    if len(parts) == 2:
        abbr = _US_STATES.get(parts[1].strip().lower())
        if abbr:
            s = f"{parts[0].strip()}, {abbr}"
    return s or None, is_remote


def _split_skill(raw: str) -> list[str]:
    s = re.sub(r'\s*\([^)]*\)', '', raw).strip()
    if not s:
        return []
    if '/' in s:
        return [part.strip() for part in s.split('/') if part.strip()]
    return [s]


def _normalize_skills(skill_groups: list, skills_map: dict) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for group in skill_groups:
        category = group.get('category') or ''
        for raw_item in group.get('items', []):
            for part in _split_skill(raw_item):
                canonical = skills_map.get(part, part)
                if canonical.lower() in seen:
                    continue
                seen.add(canonical.lower())
                result.append({'raw': part, 'canonical': canonical, 'category': category})
    return result


def normalize(
    extracted_path: Path,
    normalized_dir: Path,
    *,
    force: bool = False,
) -> dict:
    normalized_dir.mkdir(exist_ok=True)

    with open(extracted_path) as f:
        extracted = json.load(f)

    file_id = extracted['file_id']
    out_path = normalized_dir / f'{file_id}.json'

    if out_path.exists() and not force:
        print(f'[skip] {file_id} already normalized')
        return {'file_id': file_id, 'status': 'skipped'}

    experiences = []
    for exp in extracted.get('experiences', []):
        loc_canonical, is_remote = _normalize_location(exp.get('location'))
        experiences.append({
            **exp,
            'company_canonical': _normalize_company(exp.get('company', '')),
            'location_canonical': loc_canonical,
            'is_remote': is_remote,
            'start_date_iso': _parse_date_iso(exp.get('start_date')),
            'end_date_iso': _parse_date_iso(exp.get('end_date')),
        })

    education = []
    for edu in extracted.get('education', []):
        gd = edu.get('graduation_date')
        education.append({
            **edu,
            'graduation_date_iso': _parse_date_iso(gd),
            'is_expected': _is_expected_date(gd),
        })

    awards = []
    for award in extracted.get('awards', []):
        awards.append({
            **award,
            'date_iso': _parse_date_iso(award.get('date')),
        })

    skills = _normalize_skills(extracted.get('skill_groups', []), _SKILLS_MAP)

    output = {
        'file_id': file_id,
        'source_uri': extracted['source_uri'],
        'normalized_at': datetime.now(timezone.utc).isoformat(),
        'normalizer_version': 1,
        'contact': extracted.get('contact'),
        'experiences': experiences,
        'education': education,
        'projects': extracted.get('projects', []),
        'skill_groups': extracted.get('skill_groups', []),
        'skills': skills,
        'awards': awards,
        'other_sections': extracted.get('other_sections', []),
    }

    out_path.write_text(json.dumps(output, indent=2))
    print(
        f'[ok] {file_id}: '
        f'{len(experiences)} exp, '
        f'{len(education)} edu, '
        f'{len(skills)} skills'
        f' → {out_path}'
    )
    return {'file_id': file_id, 'status': 'ok'}

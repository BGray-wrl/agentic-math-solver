from pathlib import Path
import csv, re

tex_path = Path('erdos-aletheia/Erdos.tex')
text = tex_path.read_text()
BEGIN_RE = re.compile(r'\\begin\{(problem|solution)\}\{')

def parse_braced(s, i):
    assert s[i] == '{'
    depth = 0
    out = []
    j = i
    while j < len(s):
        ch = s[j]
        if ch == '{':
            depth += 1
            if depth > 1:
                out.append(ch)
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return ''.join(out), j + 1
            out.append(ch)
        else:
            out.append(ch)
        j += 1
    raise ValueError('Unmatched brace')

items = []
for m in BEGIN_RE.finditer(text):
    env = m.group(1)
    title_start = m.end() - 1
    title, after_title = parse_braced(text, title_start)
    end_token = f'\\end{{{env}}}'
    end_idx = text.find(end_token, after_title)
    body = text[after_title:end_idx].strip()
    items.append({'env': env, 'title': title, 'body': body, 'start': m.start(), 'end': end_idx + len(end_token)})

problems = [x for x in items if x['env'] == 'problem']
solutions = [x for x in items if x['env'] == 'solution']

level_map = {
    '652': 'Negligible Novelty', '654': 'Negligible Novelty', '1040': 'Negligible Novelty',
    '1051': 'Minor Novelty', '397': 'Independent Rediscovery', '659': 'Independent Rediscovery',
    '935': 'Independent Rediscovery', '1089': 'Independent Rediscovery', '333': 'Literature Identification',
    '591': 'Literature Identification', '705': 'Literature Identification', '992': 'Literature Identification',
    '1105': 'Literature Identification', '75': 'Underspecified Example',
}
category_map = {
    '75': 'Graph Theory', '333': 'Additive Number Theory', '397': 'Number Theory', '591': 'Ramsey Theory',
    '652': 'Discrete Geometry', '654': 'Discrete Geometry', '659': 'Discrete Geometry', '705': 'Graph Theory',
    '935': 'Number Theory', '992': 'Discrepancy Theory', '1040': 'Complex Analysis', '1051': 'Number Theory',
    '1089': 'Discrete Geometry', '1105': 'Ramsey Theory',
}
source = 'https://github.com/google-deepmind/superhuman/tree/main/aletheia/Erdos'

rows = []
for i, p in enumerate(problems):
    next_problem_start = problems[i+1]['start'] if i+1 < len(problems) else len(text)
    sol = next(s for s in solutions if s['start'] > p['end'] and s['start'] < next_problem_start)
    num = re.findall(r'(\d+)', p['title'])[-1]
    rows.append({
        'Problem ID': f'erdos-{num}-aletheia',
        'Problem': p['body'],
        'Solution': sol['body'],
        'Category': category_map.get(num, 'None/NA'),
        'Level': level_map.get(num, 'None/NA'),
        'Source': source,
    })

with Path('erdos_problem_solution_pairs.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['Problem ID','Problem','Solution','Category','Level','Source'])
    writer.writeheader()
    writer.writerows(rows)

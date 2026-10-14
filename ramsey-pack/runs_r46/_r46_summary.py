import json

base = r'D:\myagent\ramsey-pack'
sw = json.load(open(base + r'\_r46_sweep.json', encoding='utf-8-sig'))['sweep']
fc = {r['n']: r for r in json.load(open(base + r'\_r46_full_count.json', encoding='utf-8'))}
cc = {r['n']: r for r in json.load(open(base + r'\_r46_crosscheck.json', encoding='utf-8'))}

hdr = ['n', 'sweep(A)', 'fullcount(A)', 'direct(D)', 'A==D full',
       'A==C full(verifier)', 'space', 'sec(A)', 'samples', 'disagreements']
print(' | '.join(hdr))
for r in sw:
    n = r['n']
    c = cc[n]
    print(' | '.join([
        str(n), r['status'], str(fc[n]['solutions']), str(c['full_scan_D_count']),
        str(c['full_scan_A_vs_D_agree']),
        str(c.get('full_scan_A_vs_C_agree')),
        f"{r['space']:,}", str(r['seconds']), str(c['samples_crosschecked']),
        str(len(c['sample_disagreements'])),
    ]))

tot = sum(r['space'] for r in sw)
print('TOTAL members exhaustively checked over n=36..41 =', f'{tot:,}')


def sequence(rows):
    by_arrival = sorted(rows, key=lambda r: (r['received'], r['line'], r.get('source', 'SCAN')))
    high_water, prepared = {}, []
    for row in by_arrival:
        key = row['tag'], row['leg']
        effective = row['effective']
        # 高水位跨凭据来源维护：车单/回执先到，逐件撤下后到时同样按收件序判迟到
        previous = high_water.get(key, effective)
        prepared.append(dict(row, late=effective < previous))
        high_water[key] = max(previous, effective)
    return sorted(prepared, key=lambda r: (r['tag'], r['leg'], r['effective'], r['received'],
                                           r['line'], r.get('source', 'SCAN')))

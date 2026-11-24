from itertools import groupby
from .radio import sequence

# 车单先列待证（CART_LISTED 不改变既有装载/撤下末态），整车回执与逐件 LOAD 同权
TRANSITIONS = {
    'CART_LISTED': {'UNSEEN': 'PENDING', 'PENDING': 'PENDING', 'LOADED': 'LOADED',
                    'OFFLOADED': 'OFFLOADED', 'CONFLICT': 'CONFLICT'},
    'LOAD': {'UNSEEN': 'LOADED', 'PENDING': 'LOADED', 'LOADED': 'LOADED',
             'OFFLOADED': 'LOADED', 'CONFLICT': 'LOADED'},
    'OFFLOAD': {'UNSEEN': 'OFFLOADED', 'PENDING': 'OFFLOADED', 'LOADED': 'OFFLOADED',
                'OFFLOADED': 'OFFLOADED', 'CONFLICT': 'OFFLOADED'},
}


def replay(rows):
    timeline, states, conflicts, repeats = [], [], [], []
    for (tag, leg), stream in groupby(sequence(rows), key=lambda r: (r['tag'], r['leg'])):
        state, sources = 'UNSEEN', []
        for _, same_time in groupby(stream, key=lambda r: r['effective']):
            group = list(same_time)
            motions = {r['action'] for r in group} - {'SORT', 'CART_LISTED'}
            before = state
            if len(motions) == 2:
                state = 'CONFLICT'
                conflicts.extend(dict(r, reason='SIMULTANEOUS') for r in group if r['action'] in motions)
            else:
                for r in group:
                    state = TRANSITIONS.get(r['action'], {}).get(state, state)
            sources.extend(r['line'] for r in group)
            seen = set()
            for r in group:
                if r['action'] in seen:
                    repeats.append(dict(r, reason='RF_REPEAT'))
                else:
                    timeline.append(dict(r, before=before, after=state))
                seen.add(r['action'])
        states.append(dict(tag=tag, leg=leg, state=state, source_lines=sorted(set(sources))))
    return dict(rows=timeline, states=states, isolated=conflicts, repeats=repeats,
                counts=dict(late=sum(row['late'] for row in timeline), states=len(states), conflicts=len(conflicts)))

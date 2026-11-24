from app.input import sample
from app.modules.loading.service import loading
from app.pipeline import compute

LEGS = {'LA-1': {'leg': 'LA-1'}, 'LA-2': {'leg': 'LA-2'}}
CARTS_HEADER = 'record,cart,tag,leg,effective,received\n'
RECEIPTS_HEADER = 'receipt,cart,leg,status,effective,received\n'
T = '2026-11-22T08:{m:02d}:00+08:00'


def carts(*rows):
    return CARTS_HEADER + ''.join(','.join(row) + '\n' for row in rows)


def receipts(*rows):
    return RECEIPTS_HEADER + ''.join(','.join(row) + '\n' for row in rows)


def ramp():
    return compute(sample('ramp'))


def find(rows, tag):
    return next(r for r in rows if r['tag'] == tag)


def cart_only():
    return loading(carts(('K1', 'CT-A', 'T1', 'LA-1', T.format(m=2), T.format(m=3))),
                   receipts(('R9', 'CT-Z', 'LA-2', 'VOID', T.format(m=8), T.format(m=9))), LEGS)


def test_cart_alone_is_pending():
    stage = cart_only()
    cart_event, = (e for e in stage['events'] if e['source'] == 'CART')
    assert (cart_event['action'], cart_event['tag']) == ('CART_LISTED', 'T1')


def test_receipt_turns_matching_cart_into_load_evidence():
    cart = carts(('K1', 'CT-A', 'T1', 'LA-1', T.format(m=2), T.format(m=3)))
    receipt = receipts(('R1', 'CT-A', 'LA-1', 'ISSUED', T.format(m=5), T.format(m=6)),
                       ('R9', 'CT-Z', 'LA-2', 'VOID', T.format(m=8), T.format(m=9)))
    stage = loading(cart, receipt, LEGS)
    event, = (e for e in stage['events'] if e['source'] == 'RECEIPT')
    assert (event['action'], event['tag'], event['event']) == ('LOAD', 'T1', 'R1')


def test_receipt_without_matching_cart_is_isolated():
    cart = carts(('K1', 'CT-OTHER', 'T9', 'LA-2', T.format(m=2), T.format(m=3)))
    receipt = receipts(('R1', 'CT-Z', 'LA-1', 'ISSUED', T.format(m=5), T.format(m=6)))
    stage = loading(cart, receipt, LEGS)
    assert not any(e['source'] == 'RECEIPT' for e in stage['events'])
    assert any(r['reason'] == 'RECEIPT_CART_MISSING' for r in stage['isolated'])


# 规则 3：迟到的逐件撤下，生效在整车装机之后，回放改判已撤下
def test_late_piece_offload_overturns_receipt():
    result = ramp()
    rows = [r for r in result['replay']['rows'] if r['tag'] == 'T1001']
    assert [(r['source'], r['action'], r['after']) for r in rows] == [
        ('CART', 'CART_LISTED', 'PENDING'), ('RECEIPT', 'LOAD', 'LOADED'), ('scans.csv', 'OFFLOAD', 'OFFLOADED')]
    assert find(result['exceptions']['rows'], 'T1001')['status'] == 'not_loaded'


def test_late_flag_across_sources():
    # 回执先到且生效较新，逐件撤下后到、生效更旧：跨来源高水位仍判迟到
    from app.modules.replay.radio import sequence
    rows = [
        dict(source='RECEIPT', tag='T1', leg='LA-1', action='LOAD', line=1,
             effective='2026-11-22T08:05:00+08:00', received='2026-11-22T08:06:00+08:00'),
        dict(source='scans.csv', tag='T1', leg='LA-1', action='OFFLOAD', line=2,
             effective='2026-11-22T08:04:00+08:00', received='2026-11-22T08:31:00+08:00'),
    ]
    by_arrival = {r['source']: r['late'] for r in sequence(rows)}
    assert by_arrival == {'RECEIPT': False, 'scans.csv': True}


def test_on_time_offload_also_overturns_receipt():
    result = ramp()
    assert find(result['exceptions']['rows'], 'T1003')['status'] == 'not_loaded'


# 规则 4：同牌同时列在两个已装航段的车单上，两个航段都先列待证
def test_bag_on_two_cart_legs_both_pending():
    result = ramp()
    states = {(s['leg']): s['state'] for s in result['replay']['states'] if s['tag'] == 'T1004'}
    assert states == {'LA-1': 'PENDING', 'LA-2': 'PENDING'}
    decision = find(result['exceptions']['rows'], 'T1004')
    assert (decision['status'], decision['reason']) == ('pending', 'NO_LOAD')


# 规则 5：整车回执作废，只靠该回执的行李退回待证
def test_void_receipt_drops_bag_back_to_pending():
    result = ramp()
    voided = [r for r in result['loading']['receipts'] if r['status'] == 'VOID']
    assert {r['receipt'] for r in voided} == {'R2', 'R3', 'R4'}
    assert find(result['exceptions']['rows'], 'T1004')['status'] == 'pending'


# 规则 5 后半句：另有有效逐件装机凭据的照常算已装
def test_piece_load_survives_void_receipt():
    result = ramp()
    decision = find(result['exceptions']['rows'], 'T1005')
    assert decision['status'] == 'loaded' and decision['reason'] is None


def test_ramp_ledger_tracks_replay_final_states():
    result = ramp()
    assert result['ledger']['counts'] == dict(
        manifest=5, loaded=2, pending=1, not_loaded=2, unlisted=0, wrong_bags=0, wrong_legs=0)
    assert result['ledger']['balanced']


def test_unknown_leg_isolated():
    stage = loading(carts(('K1', 'CT-A', 'T1', 'VOID', T.format(m=2), T.format(m=3))),
                    receipts(('R9', 'CT-Z', 'LA-2', 'VOID', T.format(m=8), T.format(m=9))), LEGS)
    assert stage['isolated'][0]['reason'] == 'CART_UNKNOWN'


def test_duplicate_cart_line_isolated():
    row = ('K1', 'CT-A', 'T1', 'LA-1', T.format(m=2), T.format(m=3))
    stage = loading(carts(row, row),
                    receipts(('R9', 'CT-Z', 'LA-2', 'VOID', T.format(m=8), T.format(m=9))), LEGS)
    assert any(r['reason'] == 'CART_DUPLICATE' for r in stage['isolated'])


def test_void_receipt_creates_no_load_event():
    cart = carts(('K1', 'CT-A', 'T1', 'LA-1', T.format(m=2), T.format(m=3)))
    receipt = receipts(('R1', 'CT-A', 'LA-1', 'VOID', T.format(m=5), T.format(m=6)))
    stage = loading(cart, receipt, LEGS)
    assert [e['source'] for e in stage['events']] == ['CART']
    assert stage['receipts'][0]['reason'] == 'RECEIPT_VOID'


def test_contradictory_receipt_id_isolated():
    cart = carts(('K1', 'CT-A', 'T1', 'LA-1', T.format(m=2), T.format(m=3)))
    receipt = receipts(
        ('R1', 'CT-A', 'LA-1', 'ISSUED', T.format(m=5), T.format(m=6)),
        ('R1', 'CT-A', 'LA-2', 'ISSUED', T.format(m=5), T.format(m=6)))
    stage = loading(cart, receipt, LEGS)
    assert any(r['reason'] == 'RECEIPT_DUPLICATE' for r in stage['isolated'])


def test_identical_receipt_repeat_is_tolerated():
    cart = carts(('K1', 'CT-A', 'T1', 'LA-1', T.format(m=2), T.format(m=3)))
    line = ('R1', 'CT-A', 'LA-1', 'ISSUED', T.format(m=5), T.format(m=6))
    stage = loading(cart, receipts(line, line), LEGS)
    assert stage['counts']['receipts'] == 1 and not stage['isolated']
    assert len(stage['events']) == 2  # 一条车单 + 一条回执装机


def test_isolated_rows_carry_source_label():
    stage = cart_only()
    assert {row['source_name'] for row in stage['isolated']} == {'整车回执'}


def test_loading_stage_api(desk):
    payload = desk.post('/api/stage/loading', json={'sample': 'ramp'}).json
    assert payload['counts']['voided'] == 3 and payload['counts']['rejected'] == 0


def test_cart_listing_does_not_resurrect_offload():
    from app.modules.replay.service import replay
    rows = [
        dict(source='scans.csv', event='E1', tag='T3', leg='L1', action='OFFLOAD', line=1,
             effective='2026-11-22T08:05:00+08:00', received='2026-11-22T08:05:00+08:00', late=False),
        dict(source='CART', event='K1', tag='T3', leg='L1', action='CART_LISTED', line=2,
             effective='2026-11-22T08:06:00+08:00', received='2026-11-22T08:06:00+08:00', late=False),
    ]
    assert replay(rows)['states'][0]['state'] == 'OFFLOADED'


def test_receipt_and_piece_load_are_not_rf_repeat():
    from app.modules.replay.service import replay
    rows = [
        dict(source='RECEIPT', event='R1', tag='T2', leg='L1', action='LOAD', line=1,
             effective='2026-11-22T08:05:00+08:00', received='2026-11-22T08:06:00+08:00', late=False),
        dict(source='scans.csv', event='E1', tag='T2', leg='L1', action='LOAD', line=2,
             effective='2026-11-22T08:07:00+08:00', received='2026-11-22T08:07:00+08:00', late=False),
    ]
    out = replay(rows)
    assert out['repeats'] == [] and out['states'][0]['state'] == 'LOADED'


def test_archive_and_evidence_cover_five_files(desk):
    saved = desk.post('/api/archive', json={'sample': 'ramp'}).json
    payload = desk.get(f"/api/evidence/{saved['id']}").json
    assert {row['source'] for row in payload['rows']} == set(sample('ramp'))
    assert desk.get(f"/api/evidence/{saved['id']}/export").status_code == 200

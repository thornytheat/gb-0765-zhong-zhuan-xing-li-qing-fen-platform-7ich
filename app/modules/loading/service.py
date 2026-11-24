from collections import Counter, defaultdict

from app.clock import utc
from app.modules.scans.csvio import read_table
from app.modules.scans.normalize import SENTINELS

CART_FIELDS = ('record', 'cart', 'tag', 'leg', 'effective', 'received')
RECEIPT_FIELDS = ('receipt', 'cart', 'leg', 'status', 'effective', 'received')
RECEIPT_STATES = {'ISSUED', 'VOID'}
# 回放动作统一接入：车单是待证占位，有效整车回执转已装凭据
ACTION_BY_SOURCE = {'CART': 'CART_LISTED', 'RECEIPT': 'LOAD'}


def _clock(row, fields):
    for field in fields:
        row[field] = row[field].strip()
    if any(row[field] in SENTINELS for field in fields):
        return 'MISSING'
    try:
        row['effective'], row['received'] = utc(row['effective']), utc(row['received'])
    except ValueError:
        return 'TIME'
    if row['received'] < row['effective']:
        return 'TIME'
    return None


def _carts(text, legs):
    rows, rejected, counts = read_table(text, CART_FIELDS, 'carts.csv')
    events, seen = [], {}
    for row in rows:
        reason = _clock(row, CART_FIELDS)
        if reason is None and row['leg'] not in legs:
            reason = 'CART_UNKNOWN'
        key = (row['cart'], row['tag'], row['leg'])
        if reason is None and key in seen:
            reason = 'CART_DUPLICATE'
        if reason:
            rejected.append(dict(row, reason=reason))
            continue
        seen[key] = row['line']
        events.append(dict(source='CART', event=row['record'], cart=row['cart'], tag=row['tag'],
                           leg=row['leg'], action=ACTION_BY_SOURCE['CART'],
                           effective=row['effective'], received=row['received'], line=row['line']))
    counts.update(events=len(events), rejected=len(rejected))
    return events, rejected, counts


def _receipts(text, legs, cart_keys):
    rows, rejected, counts = read_table(text, RECEIPT_FIELDS, 'receipts.csv')
    events, ledger, seen = [], [], {}
    for row in rows:
        reason = _clock(row, RECEIPT_FIELDS)
        if reason is None and row['status'] not in RECEIPT_STATES:
            reason = 'RECEIPT_STATUS'
        if reason is None and row['leg'] not in legs:
            reason = 'RECEIPT_UNKNOWN'
        if reason is None and row['receipt'] in seen:
            prior = seen[row['receipt']]
            if any(prior[field] != row[field] for field in ('cart', 'leg', 'status', 'effective', 'received')):
                reason = 'RECEIPT_DUPLICATE'
            else:
                # 同回执号完全重报：采信首次收件，不重复建台账与装机凭据
                continue
        if reason:
            rejected.append(dict(row, reason=reason))
            continue
        seen[row['receipt']] = row
        matched = (row['cart'], row['leg']) in cart_keys
        if not matched:
            rejected.append(dict(row, reason='RECEIPT_CART_MISSING'))
            continue
        ledger.append(dict(receipt=row['receipt'], cart=row['cart'], leg=row['leg'],
                           status=row['status'], effective=row['effective'],
                           received=row['received'], line=row['line'],
                           source_name='整车回执',
                           reason=None if row['status'] == 'ISSUED' else 'RECEIPT_VOID'))
        if row['status'] == 'ISSUED':
            # 车单与整车回执对上同一航段后，整车回执成为装机凭据
            events.append(dict(source='RECEIPT', event=row['receipt'], cart=row['cart'], tag=None,
                               leg=row['leg'], action=ACTION_BY_SOURCE['RECEIPT'],
                               effective=row['effective'], received=row['received'], line=row['line']))
    counts.update(events=len(events), receipts=len(ledger), voided=sum(1 for r in ledger if r['status'] == 'VOID'),
                  rejected=len(rejected))
    return events, rejected, counts, ledger


def loading(carts_text, receipts_text, legs):
    cart_events, cart_rejected, cart_counts = _carts(carts_text, legs)
    cart_keys = {(event['cart'], event['leg']) for event in cart_events}
    receipt_events, receipt_rejected, receipt_counts, receipt_rows = _receipts(receipts_text, legs, cart_keys)
    # 有效回执按航段把车单上的每一件都扩成装机凭据；作废回执不扩
    tags_by_cart_leg = defaultdict(list)
    for event in cart_events:
        tags_by_cart_leg[(event['cart'], event['leg'])].append(event['tag'])
    expanded = []
    for event in receipt_events:
        for tag in sorted(tags_by_cart_leg[(event['cart'], event['leg'])]):
            expanded.append(dict(event, tag=tag))
    rejected = sorted(cart_rejected + receipt_rejected, key=lambda row: (row['source'], row['line']))
    for row in rejected:
        row['source_name'] = '车单' if row['source'] == 'carts.csv' else '整车回执'
    counts = dict(cart_rows=cart_counts['source_rows'], receipt_rows=receipt_counts['source_rows'],
                  cart_events=len(cart_events), receipts=receipt_counts['receipts'],
                  receipt_events=len(expanded), voided=receipt_counts['voided'],
                  rejected=len(rejected), reasons=dict(Counter(row['reason'] for row in rejected)))
    return dict(events=cart_events + expanded, receipts=receipt_rows, isolated=rejected, counts=counts)

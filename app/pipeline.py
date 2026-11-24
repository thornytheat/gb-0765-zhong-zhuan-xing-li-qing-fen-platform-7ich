from .modules.scans.service import ingest
from .modules.legs.contracts import references
from .modules.legs.service import associate
from .modules.loading.service import loading
from .modules.replay.service import replay
from .modules.exceptions.service import classify
from .modules.ledger.service import reconcile


def compute(files, until=None):
    scans = ingest(files['scans.csv'])
    if until == 'scans':
        return scans
    legs, manifest, master_errors = references(files['legs.csv'], files['manifest.csv'])
    linked = associate(scans['rows'], legs)
    linked.update(legs=list(legs.values()), manifest=list(manifest.values()), reference_isolated=master_errors)
    if until == 'legs':
        return linked
    creds = loading(files['carts.csv'], files['receipts.csv'], legs)
    if until == 'loading':
        return creds
    history = replay(linked['rows'] + creds['events'])
    if until == 'replay':
        return history
    undecided = scans['isolated'] + linked['isolated'] + creds['isolated']
    decisions = classify(manifest, history['states'], undecided)
    if until == 'exceptions':
        return decisions
    ledger = reconcile(decisions, legs, scans['counts'])
    if until == 'ledger':
        return ledger
    return dict(scans=scans, legs=linked, loading=creds, replay=history, exceptions=decisions, ledger=ledger)

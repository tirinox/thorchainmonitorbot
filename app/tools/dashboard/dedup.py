from lib.db import DB
from lib.money import format_percent
from notify.dup_stop import TxDeduplicator


async def dedup_dashboard_info(db: DB):
    items = [
        "scanner:last_seen", 'route:seen_tx', 'TxCount', 'VolumeRecorder', "loans:announced-hashes",
        'RunePool:announced-hashes', 'ss-started:announced-hashes', 'TradeAcc:announced-hashes',
        'large-tx:announced-hashes'
    ]

    summary = []
    for name in items:
        dedup = TxDeduplicator(db, name)
        bit_count = await dedup.bit_count()
        size = await dedup.length()
        summary.append({
            'name': name,
            'bit_count': bit_count,
            'size': size,
            'fill_rate': format_percent(bit_count, size),
            'total_requests': dedup.total_requests,
            'positive_requests': dedup.positive_requests,
            'success_rate': format_percent(dedup.positive_requests, dedup.total_requests),
        })

    return summary

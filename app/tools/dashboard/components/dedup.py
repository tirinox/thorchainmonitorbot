from lib.money import format_percent
from notify.dup_stop import TxDeduplicator


async def dedup_dashboard_info(d):
    items = [
        "scanner:last_seen", 'route:seen_tx', 'TxCount', 'VolumeRecorder',
        'RunePool:announced-hashes', 'ss-started:announced-hashes', 'TradeAcc:announced-hashes',
        'large-tx:announced-hashes'
    ]

    summary = []
    for name in items:
        dedup = TxDeduplicator(d.db, name)
        bit_count = await dedup.bit_count()
        size = await dedup.length()
        stats = await dedup.load_stats()
        summary.append({
            'Names': name,
            'Bits 1': bit_count,
            'Size': size,
            'Fill %': format_percent(bit_count, size),
            'Total read': stats['total_requests'],
            'Positive': stats['positive_requests'],
            'Success': format_percent(stats['positive_requests'], stats['total_requests']),
            'Writes': stats['write_requests'],
        })

    return summary

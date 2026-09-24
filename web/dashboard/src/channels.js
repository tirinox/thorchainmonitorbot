const ICONS = {
    telegram: 'pi pi-telegram',
    discord: 'pi pi-discord',
    slack: 'pi pi-slack',
    twitter: 'pi pi-twitter',
}

export const channelIcon = (type) => ICONS[type] || 'pi pi-megaphone'

export const channelTitle = (type) => type ? type[0].toUpperCase() + type.slice(1) : 'Unknown'

export const channelLabel = (c) => `${channelTitle(c.type)} · ${c.channel} · ${c.lang}`

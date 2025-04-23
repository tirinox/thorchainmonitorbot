function secondsToDaysHours(seconds) {
    const days = Math.floor(seconds / (24 * 3600));
    const hours = Math.floor((seconds % (24 * 3600)) / 3600);

    const parts = [];

    if (days > 0) {
        const dayLabel = days === 1 ? "Day" : "Days";
        parts.push(`${days} ${dayLabel}`);
    }

    if (hours > 0) {
        const hourLabel = hours === 1 ? "Hour" : "Hours";
        parts.push(`${hours} ${hourLabel}`);
    }

    return parts.join(" ") || "0 Hours"; // fallback if both are 0
}
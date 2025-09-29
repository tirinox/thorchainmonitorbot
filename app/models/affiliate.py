from typing import List, Optional

from pydantic import BaseModel, Field

from models.base import IntFromStr, FloatFromStr


class ThornameData(BaseModel):
    thorname: str
    count: IntFromStr
    volume: FloatFromStr
    volume_usd: FloatFromStr = Field(alias="volumeUSD")


class AffiliateInterval(BaseModel):
    start_time: int = Field(alias="startTime")
    end_time: int = Field(alias="endTime")
    count: IntFromStr
    thornames: Optional[List[ThornameData]] = None
    volume: FloatFromStr
    volume_usd: FloatFromStr = Field(alias="volumeUSD")

    def sort_thornames_by_usd_volume(self):
        self.thornames.sort(key=lambda x: x.volume_usd, reverse=True)
        return self

    @classmethod
    def sum_of_intervals_per_thorname(cls, intervals: List['AffiliateInterval']) -> 'AffiliateInterval':
        acc = {}
        total_count = 0
        total_volume = 0
        total_volume_usd = 0
        for interval in intervals:
            if not interval.thornames:
                continue
            for tn in interval.thornames:
                if tn.thorname not in acc:
                    acc[tn.thorname] = ThornameData(thorname=tn.thorname, count=0, volume=0.0, volumeUSD=0.0)
                acc[tn.thorname].count += tn.count
                acc[tn.thorname].volume += tn.volume
                acc[tn.thorname].volume_usd += tn.volume_usd

            total_count += interval.count
            total_volume += interval.volume
            total_volume_usd += interval.volume_usd

        return AffiliateInterval(
            startTime=min(i.start_time for i in intervals) if intervals else 0,
            endTime=max(i.end_time for i in intervals) if intervals else 0,
            thornames=list(acc.values()),
            count=total_count,
            volume=total_volume,
            volumeUSD=total_volume_usd
        )


class AffiliateHistoryResponse(BaseModel):
    meta: AffiliateInterval
    intervals: List[AffiliateInterval]


class AffiliateCollector(BaseModel):
    total_usd: float
    count: int
    prev_total_usd: float
    prev_count: int
    thorname: str
    display_name: str
    logo: str

from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, model_validator


class SchedVariant:
    INTERVAL = "interval"
    CRON = "cron"
    DATE = "date"


class IntervalCfg(BaseModel):
    weeks: Optional[int] = None
    days: Optional[int] = None
    hours: Optional[int] = None
    minutes: Optional[int] = None
    seconds: Optional[int] = None

    @model_validator(mode="after")
    def validate_interval(self):
        if not any([self.weeks, self.days, self.hours, self.minutes, self.seconds]):
            raise ValueError("Interval trigger requires at least one time field")
        return self

    @property
    def human_readable(self) -> str:
        parts = []
        if self.weeks:
            parts.append(f"{self.weeks} week")
        if self.days:
            parts.append(f"{self.days} day")
        if self.hours:
            parts.append(f"{self.hours} hour")
        if self.minutes:
            parts.append(f"{self.minutes} min")
        if self.seconds:
            parts.append(f"{self.seconds} sec")
        return ", ".join(parts)


class CronCfg(BaseModel):
    year: Optional[str] = None
    month: Optional[str] = None
    day: Optional[str] = None
    week: Optional[str] = None
    day_of_week: Optional[str] = None
    hour: Optional[str] = None
    minute: Optional[str] = None
    second: Optional[str] = None

    @property
    def human_readable(self) -> str:
        parts = []
        if self.year:
            parts.append(f"year={self.year}")
        if self.month:
            parts.append(f"month={self.month}")
        if self.day:
            parts.append(f"day={self.day}")
        if self.week:
            parts.append(f"week={self.week}")
        if self.day_of_week:
            parts.append(f"day_of_week={self.day_of_week}")
        if self.hour:
            parts.append(f"hour={self.hour}")
        if self.minute:
            parts.append(f"minute={self.minute}")
        if self.second:
            parts.append(f"second={self.second}")
        return ", ".join(parts)


class DateCfg(BaseModel):
    run_date: datetime

    @property
    def human_readable(self) -> str:
        return self.run_date.strftime("%Y-%m-%d %H:%M:%S")


class SchedJobCfg(BaseModel):
    id: str
    func: str
    enabled: bool = True
    variant: Literal["interval", "cron", "date"]

    interval: Optional[IntervalCfg] = None
    cron: Optional[CronCfg] = None
    date: Optional[DateCfg] = None

    # APScheduler extras
    max_instances: int = 1
    coalesce: bool = True
    misfire_grace_time: Optional[int] = None

    @model_validator(mode="after")
    def validate_by_variant(self):
        if self.variant == SchedVariant.INTERVAL and not self.interval:
            raise ValueError("variant=interval requires 'interval' config block")

        if self.variant == SchedVariant.CRON and not self.cron:
            raise ValueError("variant=cron requires 'cron' config block")

        if self.variant == SchedVariant.DATE and not self.date:
            raise ValueError("variant=date requires 'date' config block")

        return self

    def to_add_job_args(self) -> dict:
        args = {
            "trigger": self.variant,
            "id": self.id,
            "replace_existing": True,
            "max_instances": self.max_instances,
            "coalesce": self.coalesce,
        }

        if self.misfire_grace_time is not None:
            args["misfire_grace_time"] = self.misfire_grace_time

        # параметры для конкретного триггера
        if self.variant == SchedVariant.INTERVAL:
            args.update(self.interval.model_dump(exclude_none=True))

        elif self.variant == SchedVariant.CRON:
            args.update(self.cron.model_dump(exclude_none=True))

        elif self.variant == SchedVariant.DATE:
            args.update(self.date.model_dump())

        return args

from fastapi import Request

from dashboard.context import DashboardContext


def get_ctx(request: Request) -> DashboardContext:
    return request.app.state.ctx

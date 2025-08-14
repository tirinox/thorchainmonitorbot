from lib.depcont import DepContainer


async def stats_dashboard_info(d: DepContainer):
    users = await d.settings_manager.all_users_having_settings()
    user_settings_count = len(users)
    bot_user_count = await d.settings_manager.bot_user_count()
    return {
        'user_settings_count': user_settings_count,
        'bot_user_count': bot_user_count,
    }

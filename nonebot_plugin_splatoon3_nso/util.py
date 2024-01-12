from .utils.bot import *


def get_or_init(dictionary: dict, key: str, default=None):
    """字典赋值"""
    if default is None:
        default = {}
    if dictionary.get(key) is None:
        dictionary.update({key: default})
        return default
    else:
        return dictionary.get(key)


class ChannelInfo:
    """类 服务器或频道信息 ChannelInfo"""

    def __init__(
            self,
            bot_adapter,
            bot_id,
            source_type,
            source_id,
            source_name,
            owner_id,
            source_parent_id=None,
            source_parent_name=None,
    ):
        self.bot_adapter = bot_adapter
        self.bot_id = bot_id
        self.source_type = source_type
        self.source_id = source_id
        self.source_name = source_name
        self.owner_id = owner_id
        self.source_parent_id = source_parent_id
        self.source_parent_name = source_parent_name


async def get_channel_info(bot: any, source_type: str, _id: str, _parent_id: str = None) -> ChannelInfo:
    """获取服务器或频道信息"""
    global guilds_info
    bot_adapter = bot.adapter.get_name()
    bot_id = bot.self_id
    # 获取字典信息
    adapter_group = guilds_info.get(bot_adapter)
    if adapter_group is not None:
        account_group = adapter_group.get(bot_id)
        if account_group is not None:
            type_group = account_group.get(source_type)
            if type_group is not None:
                guild_info = type_group.get(_id)
                if guild_info is not None:
                    owner_id = guild_info["owner_id"]
                    source_name = guild_info["source_name"]
                    _parent_name = guild_info["source_name"]
                    return ChannelInfo(
                        bot_adapter, bot_id, source_type, _id, source_name, owner_id, _parent_id, _parent_name
                    )
    # 写入新记录
    owner_id = ""
    source_name = ""
    _parent_name = None
    if source_type == "guild":
        if isinstance(bot, Kook_Bot):
            guild_info = await bot.guild_view(guild_id=_id)
            owner_id = guild_info.user_id
            source_name = guild_info.name
        elif isinstance(bot, QQ_Bot):
            guild_info = await bot.get_guild(guild_id=_id)
            owner_id = guild_info.owner_id
            source_name = guild_info.name
    elif source_type == "channel":
        if _parent_id is not None:
            # 提供了 _parent_id 说明为服务器频道
            if isinstance(bot, Kook_Bot):
                guild_info = await bot.guild_view(guild_id=_parent_id)
                _parent_name = guild_info.name

                channel_info = await bot.channel_view(target_id=_id)
                owner_id = channel_info.user_id
                source_name = channel_info.name
            elif isinstance(bot, QQ_Bot):
                guild_info = await bot.get_guild(guild_id=_parent_id)
                _parent_name = guild_info.name

                channel_info = await bot.get_channel(channel_id=_id)
                owner_id = channel_info.owner_id
                source_name = channel_info.name
        else:
            if isinstance(bot, Kook_Bot):
                channel_info = await bot.channel_view(target_id=_id)
                owner_id = channel_info.user_id
                source_name = channel_info.name
            elif isinstance(bot, QQ_Bot):
                channel_info = await bot.get_channel(channel_id=_id)
                owner_id = channel_info.owner_id
                source_name = channel_info.name
    adapter_group = get_or_init(guilds_info, bot_adapter)
    account_group = get_or_init(adapter_group, bot_id)
    type_group = get_or_init(account_group, source_type)
    type_group.update({"owner_id": owner_id})
    type_group.update({"name": source_name})
    type_group.update({"parent_id": _parent_id})
    type_group.update({"parent_name": _parent_name})
    return ChannelInfo(bot_adapter, bot_id, source_type, _id, source_name, owner_id, _parent_id, _parent_name)

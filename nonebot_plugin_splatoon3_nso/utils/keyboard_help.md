> md消息部分参考: [ElainaBot_v2 文档](https://github.com/ElainaCore/ElainaBot_v2/blob/main/PLUGIN_DEVELOPMENT.md?plain=1#5-%E6%B6%88%E6%81%AF%E5%8F%91%E9%80%81-api)

### 5.1 文本与媒体回复

```python
# 文本回复
await event.reply("Hello!")

# 带按钮回复 (完整字段参考见 5.2 节)
buttons = [
    [{'text': '回调', 'data': 'cb_1', 'type': 1},      # 回调按钮
     {'text': '输入', 'data': '/帮助', 'type': 2}],    # 填充指令到输入框
    [{'text': '链接', 'link': 'https://example.com'}],  # 链接按钮 (等同 type=0)
]
await event.reply("📌 选择操作", buttons=buttons)

# 自动撤回 (秒)
await event.reply("⏰ 5秒后撤回", auto_delete_time=5)

# 图片 (URL 或 bytes)
await event.reply_image("https://i.elaina.vin/1.png", "图片说明")
await event.reply_image(open('local.png', 'rb').read(), "本地图片")

# 语音 / 视频 / 文件
await event.reply_voice("https://example.com/audio.wav")
await event.reply_video("https://example.com/video.mp4")
await event.reply_file('/path/to/file.txt', "📄 文档", file_name="custom.txt")
```

### 5.2 按钮完整字段参考

按钮是二维数组 `list[list[dict]]` (行 × 列), 每个按钮是一个字典。

#### 核心字段

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `text` | `str` | `''` | 按钮显示文字 (**必填**) |
| `type` | `int` | `2` | 按钮类型: `0`=跳转链接 / `1`=回调 / `2`=输入指令 |
| `data` | `str` | `text` | type=0: URL; type=1: 回调标识; type=2: 填充到输入框的内容 |
| `link` | `str` | — | 快捷方式: 设置后自动设为 `type=0 + data=link` |
| `show` | `str` | `text` | 点击后显示的文字 (visited_label) |
| `style` | `int` | `1` | 样式: `0`=灰框 / `1`=蓝框蓝字 / `2`=黑框(PC 端气泡) / `3`=黑框红字 / `4`=蓝底白字 |

#### 行为字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `enter` | `bool` | 已失效，无论填写不填写，最终都会被开放平台删掉|
| `reply` | `bool` | 点击后作为引用回复发送 |
| `limit` | `int` | 点击次数限制 (`click_limit`)可能无效 |
| `tips` | `str` | 不支持时的提示文字 (`unsupport_tips`) |

#### 权限字段 (五者二选一, 优先级从上到下)

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `permission` | `dict` | 显式权限对象, 如 `{'type': 1}` |
| `role` | `list[str]` | 指定身份组 ID 列表 (频道场景) → `type=3` |
| `list` | `list[str]` | 指定用户 ID 列表 → `type=0` |
| `admin` | `bool` | 仅管理员可点 → `type=1` |
| _默认_ | — | 所有人可点 → `type=2` |

#### 按钮完整示例

```python
buttons = [
    # 第一行: 三种基础类型
    [
        {'text': '跳转官网', 'link': 'https://example.com'},        # 链接
        {'text': '点我回调', 'data': 'cb_action_1', 'type': 1},     # 回调
        {'text': '/帮助', 'type': 2},               # 输入后自动发送
    ],
    # 第二行: 权限与限制
    [
        {'text': '仅管理员', 'data': 'admin_only', 'type': 1, 'admin': True},
        {'text': '指定用户', 'data': 'specific', 'type': 1,
         'list': ['user_id_1', 'user_id_2']},
        {'text': '点击一次', 'data': 'once', 'type': 1, 'limit': 1},
    ],
    # 第三行: 样式与提示
    [
        {'text': '灰框', 'data': 's0', 'type': 1, 'style': 0},
        {'text': '黑框红字', 'data': 's3', 'type': 1, 'style': 3},
        {'text': '蓝底白字', 'data': 's4', 'type': 1, 'style': 4},
        {'text': '不支持提示', 'data': 'oops', 'type': 1,
         'tips': '该功能仅 PC 端可用'},
    ],
]
await event.reply("📌 多功能按钮面板", buttons=buttons)
```

#### 小按钮 (键盘级字号)

通过键盘级样式 `content.style.font_size` 控制整组按钮的大小 (对应官方 botgo
`CustomKeyboard.Style.FontSize`), 取值 `small` / `middle` / `large`, `small`
即「小按钮」。两种用法:

```python
# 方式一: reply 关键字 button_font_size
await event.reply("📌 小按钮面板", buttons=buttons, button_font_size='small')

# 方式二: buttons 用 dict 包装 (适用于所有发送入口, 含主动推送/频道)
await event.reply("📌 小按钮面板", buttons={'rows': buttons, 'font_size': 'small'})
```

不传则保持原默认大小。

#### 附: 扩展 prompt 按钮 (最多 3 个)

```python
# 字符串简写 (点击后自动发送 'elaina')
await event.reply("选择:", prompt_buttons=['选项A', '选项B', '选项C'])

# (文本, 样式) 元组
await event.reply("选择:", prompt_buttons=[('确认', 1), ('取消', 0)])
```

### 5.3 Ark 卡片

```python
# ark23 — 列表卡片
await event.reply_ark(23, (
    "列表卡片标题", "提示文本",
    [['项目1'], ['项目2', 'https://link.com']]))

# ark24 — 文本+图片
await event.reply_ark(24, (
    "提示", "标题", "副标题", "描述", "图片URL", "跳转URL", "图片副标题"))

# ark37 — 大图文
await event.reply_ark(37, (
    "提示", "标题", "副标题", "图片URL", "跳转URL"))
```
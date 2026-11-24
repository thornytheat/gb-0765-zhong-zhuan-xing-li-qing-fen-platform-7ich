# 数据定义

- `scans.csv` 每行一个收件。`event` 和 `tag` 是保形字符串，`flight` 为机场航班号，`leg_hint` 为可空精确航段。`action` 取 `SORT`、`LOAD`、`OFFLOAD`。`effective` 与 `received` 为带偏移 ISO 8601，后者不能早于前者。UTC 精度微秒。原因码同 `app/reasons.py`。
- `legs.csv` 含唯一 `leg`、`flight`、`start`、`end`、`destination`。窗口 `[start,end)`，用 UTC 比较。存在明确提示时仍须命中时间和航班。无提示且有多候选时隔离。`manifest.csv` 每个 `tag` 只出现一次且 `planned` 必须引用已知 `leg`。
- `carts.csv` 每行一条车单：`record`、`cart`、`leg`、`tag`、`effective`、`received`。车单先把该牌在该航段列为待证（`CART_LISTED`），未知航段按 `CART_UNKNOWN` 隔离，同车牌同牌同航段重复按 `CART_DUPLICATE` 隔离。
- `receipts.csv` 每行一份整车回执：`receipt`、`cart`、`leg`、`status`（`ISSUED`/`VOID`）、`effective`、`received`。回执必须与同车牌同航段的车单对上，否则 `RECEIPT_CART_MISSING`；同回执号内容矛盾按 `RECEIPT_DUPLICATE` 隔离，作废回执记入台账（`RECEIPT_VOID`）但不产生装机凭据。
- 原件只接受 UTF-8，可带 BOM。物理起始行号保留。重复表头计分段，空行单计，宽度不符保留整行。空文件、全空记录、仅表头分别有明确失败。`-`、`N/A`、`NULL`、`未知` 与空串都不参与必填匹配。API 中被归一化的可选提示用 `null` 表示缺提示。
- 同扫描编号按航段提示、航班、动作、行李牌和生效时刻比较。内容相同取最早收件，内容矛盾整组隔离。不同编号同牌同航段同刻同动作只改变一次状态。收件决定迟到标记（高水位跨逐件、车单、回执三类来源维护），生效决定回放。同刻相反装撤产生冲突，后续有效动作可确认新末态。
- 回放统一接入三类凭据：车单为 `CART_LISTED`（只把 `UNSEEN` 推到 `PENDING`，不改写既有装载/撤下末态），有效整车回执按航段把对应该车单的每件扩成 `LOAD`，逐件 `LOAD`/`OFFLOAD` 照常。迟到逐件撤下若生效晚于整车装机，末态改判撤下。一件行李同牌挂在两个已装航段车单上时，两个航段都先列待证。回执作废后只靠该回执的行李退回待证；另有有效逐件装机凭据的仍算已装。
- 计划段装载且无未决装撤及错装时计已装。计划段末态撤下计明确未装。其他计划件待证。错载按非计划段末态装载记录，按牌去重计件。清单外行李另外列出。列宽失配行只提供原始字段，不对其牌号做确定归属。
- 批次由规则版本与五份文件内容哈希决定。SQLite 一次提交原件和结果；同源并发使用唯一键，复算比较结果散列。证据签发核对两个摘要及守恒，归档原样含 UTF-8 BOM。

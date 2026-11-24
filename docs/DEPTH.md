# 深度登记 中转行李清分台

中转主管逐牌核对航段窗口与动作末态。跨日同航班号不能替代航段实例。关舱前用整车回执先报装机数，逐件扫齐与迟到撤下再由回放改判。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 扫描原件采信 | 查看射频重报和隔离行 | `/desk/scans` `/api/stage/scans` | `app/modules/scans/service.py` | `tests/test_scans.py` |
| M2 航段候选关联 | 核对候选段和提示 | `/desk/legs` `/api/stage/legs` | `app/modules/legs/service.py` | `tests/test_legs.py` |
| M3 装机凭据采信 | 核对车单待证、整车回执与作废 | `/desk/loading` `/api/stage/loading` | `app/modules/loading/service.py` | `tests/test_loading.py` |
| M4 扫件有序回放 | 按生效时刻核对动作 | `/desk/replay` `/api/stage/replay` | `app/modules/replay/service.py` | `tests/test_replay.py` `tests/test_loading.py` |
| M5 错载与漏扫归因 | 按牌追踪待证与错装 | `/desk/exceptions` `/api/stage/exceptions` | `app/modules/exceptions/service.py` | `tests/test_exceptions.py` |
| M6 行李去向对账 | 勾稽计划段与去向件数 | `/` `/api/stage/ledger` | `app/modules/ledger/service.py` | `tests/test_ledger.py` |
| M7 批次留档复跑 | 保存并复算原件 | `/desk/archive` `POST /api/archive` | `app/modules/archive/service.py` `app/modules/archive/store.py` | `tests/test_archive.py` |
| M8 联程证据签发 | 验摘要并下载联程证据 | `/desk/evidence` `/api/evidence/<run>/export` | `app/modules/evidence/bundle.py` | `tests/test_evidence.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-02 | 脏扫描首列 BOM | 扫描号丢失 | 解码时去首 BOM | `app/modules/scans/csvio.py` | `tests/test_scans.py::test_bom` |
| TRAP-04 | 脏扫描第 16 行重复表头 | 误计为扫描 | 计独立分段 | `app/modules/scans/csvio.py` | `tests/test_scans.py::test_sections` |
| TRAP-05 | E17 多余分隔列 | 宽度误收 | 原行隔离 | `app/modules/scans/csvio.py` | `tests/test_scans.py::test_bad_width` |
| TRAP-07 | E18 时间 N/A | 默认零时 | 空值隔离 | `app/modules/scans/normalize.py` | `tests/test_scans.py::test_sentinel` |
| TRAP-08 | 清单 000101 | 强转丢零 | 字符串关联 | `app/modules/legs/contracts.py` | `tests/test_legs.py::test_tag_preserved` |
| TRAP-11 | E03 特殊偏移重复 | 误认成不同事件 | UTC 后比较 | `app/modules/scans/normalize.py` | `tests/test_scans.py::test_equivalent_offset_duplicate` |
| TRAP-13 | E02 迟到撤下 | 收件顺序末态错误 | 标迟到后按生效回放 | `app/modules/replay/radio.py` | `tests/test_replay.py::test_late_offload_before_reload` |
| TRAP-14 | E12 同键相反动作 | 后写覆盖 | 全组隔离 | `app/modules/scans/service.py` | `tests/test_scans.py::test_conflicting_id` |
| TRAP-23 | E04 恰逢跨日换窗 | 同时匹配两段 | 左闭右开 | `app/modules/legs/service.py` | `tests/test_legs.py::test_boundary_handoff` |
| TRAP-31 | 关舱等不到逐件扫描 | 装机数报不出 | 车单先列待证、有效回执转装机凭据 | `app/modules/loading/service.py` `app/modules/replay/service.py` | `tests/test_loading.py::test_cart_alone_is_pending` `test_receipt_turns_matching_cart_into_load_evidence` |
| TRAP-32 | 整车回执含已撤行李 | 照单全算多计件 | 迟到/准时撤下按生效时刻改判撤下 | `app/modules/replay/service.py` | `tests/test_loading.py::test_late_piece_offload_overturns_receipt` `test_on_time_offload_also_overturns_receipt` |
| TRAP-33 | 同牌挂两段车单 | 先到航段独占已装 | 两航段都先列待证 | `app/modules/replay/service.py` | `tests/test_loading.py::test_bag_on_two_cart_legs_both_pending` |
| TRAP-34 | 回执作废后件数虚高 | 已装不回退 | 只靠回执的退回待证，逐件装机保留 | `app/modules/loading/service.py` `app/modules/replay/service.py` | `tests/test_loading.py::test_void_receipt_drops_bag_back_to_pending` `test_piece_load_survives_void_receipt` |
| TRAP-35 | 回执找不到车单 | 凭空生成装机 | 回执隔离不计凭据 | `app/modules/loading/service.py` | `tests/test_loading.py::test_receipt_without_matching_cart_is_isolated` |

## 装机凭据规则（关舱报数）

1. 车单只列待证：`CART_LISTED` 不把行李算已装，已装载/已撤下末态不被车单覆盖。
2. 车单与整车回执对上同一航段（同 `cart` 同 `leg`、回执 `ISSUED`）后，回放把回执认作该航段装机凭据，按车单逐件扩成 `LOAD`。
3. 迟到逐件撤下按生效时刻回放；生效在整车装机之后的，末态改判已撤下（明确未装）。
4. 一件行李同牌出现在两个已装航段的车单上时，两个航段都保持 `PENDING`，不抢先判已装。
5. 整车回执 `VOID` 后不产生装机凭据：只靠该回执的行李退回待证；另有有效逐件 `LOAD` 的照常算已装。
6. 去向对账页随回放末态更新，`清单 = 已装 + 待证 + 明确未装` 守恒。

`ramp` 样例五件覆盖规则 2–6：T1001 迟到撤下、T1002 回执装机、T1003 准时撤下、T1004 双航段待证且回执作废、T1005 回执作废但逐件装机保留。

## 对账规则

脏样例清单 12 = 3 已装 + 8 待证 + 1 明确未装，错装 2 件另列。扫描原件记录 24 = 17 采信 + 4 隔离 + 1 重报 + 1 重复表头 + 1 空行。脏样例车单/回执仅对已决件 000110 作旁证，不改变历史判定。

## 已知范围

文件内容通过限长 JSON 提交。样例为机场单站观测，时间窗由机场清单提供。扫描尾播放已采信记录的收件流（含车单与回执来源标记）。

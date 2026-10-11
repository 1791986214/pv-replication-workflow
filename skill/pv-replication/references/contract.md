# 整数帧合同：把漏动作变成可定位的问题

模板：[contract-template.json](contract-template.json)。它是 36 帧的虚构示例，包含 A/B 动作和四张效果各六帧的结构；不是这支 PV 的渲染配置，也不是通用帧率规定。真实媒体哈希、采用原画和播放记录尚未填入，初次校验应失败。复制后按真实原片改帧率、总帧数、区间及事件。

## 字段

| 字段 | 含义与检查 |
| --- | --- |
| `source` | 项目内相对路径、SHA256、帧率分子/分母、全片帧数。仅接受已确定的工作时间线；不自行处理变帧率。 |
| `interval` | 本次覆盖 `[start,end)`，不能超出源时间线。 |
| `source_events` | 连续源事件及其目标 `requirements`：物体、姿态、表情、局部动作、必要相位。改编需要在事件旁记录原状态与批准后的目标。 |
| `states` | 按时间排序的剧情状态；每个状态关联一个源事件。一个多人物事件可同时包含几个物体 requirement。 |
| `drawings` | 每个 cel 的资产、物体、姿态、表情、局部动作和相位。每项源要求必须有采用绘图。 |
| `schedule` | 每个物体每一帧由哪张已声明绘图承担；不得空缺、重叠，也不得声明绘图却从不使用。 |
| `expected_state_order` | 约定的状态顺序；避免渲染器用“魔女/正常”开关吞掉抬眼、回应、确认与释然。 |
| `owners` | 无歧义的语义区域与唯一 owner、遮罩来源。人物头部 owner 声明 whole-head / no deformation。多个 cel 可复用一个 owner；区域名应互斥。 |
| `assets` | 采用文件路径/哈希/物体/owner/几何锁定/批准状态。生成参考和落选候选放到另外的档案清单，不能混进采用清单。 |
| `layer_order` / `required_layer_order` | 实际与约定层序；接触变化另立事件配置。不是强制所有 PV 采用一个固定层序。 |
| `transitions` | 效果覆盖区间、换图帧、完全遮盖区间、改动区域、实测 `expected_cel_durations` 与效果 cel 持帧；效果必须完整画布且不能按人物裁切。 |
| `output` | 最终检查 MP4 路径/哈希。 |
| `reviews` | 原速、半速、独立审查的范围、结果、审查者、观察、输出哈希、证据路径；三个种类均必须声明真实播放，独立审查还需 `independent_of_author=true` 与 `source_continuity_checked=true`。 |

owner 的 `mask` 取 `explicit-alpha`、`semantic-tracked`、`source-explicit` 或 `none`。前两者需要项目自身实现遮罩；校验器只核对声明。颜色/连通组件可以帮助定位候选像素，不能直接成为所有权结论。`geometry_lock` 是资产生产者的具体承诺，例如“左右袜子、膝/踝锚点、鞋尖透视保持固定”；文字声明不会自动证明人体正确。

当前单个合同的 `source_events` 区间不能重叠；每个状态只有一个 `source_event_id`，且整体 `states` 区间严格连续。并行动作放入同一事件的多个物体 requirement，按全部物体的状态边界划分整数帧段；复杂镜头可以拆成多个合同。不要强行把所有连续动作压进两个相位；相位名称和数量来自实际源绘图。

## 命令与失败意义

```bash
python3 scripts/validate_contract.py contract.json
python3 scripts/validate_contract.py contract.json --root /path/to/project
python3 scripts/validate_contract.py contract.json --stage delivery --root /path/to/project
python3 scripts/test_validate_contract.py
```

- preflight 验证声明关系、全部帧覆盖、所有姿态/相位、状态顺序、owner、效果换图范围；带 `--root` 还检查源与采用文件哈希。
- delivery 另外要求已批准原画、输出文件与哈希、三个审查种类的覆盖、当前输出对应的证据文件，以及原速/半速实际播放记录。
- exit 0 是这些声明通过；exit 1 是合同不完整；exit 2 是 JSON 或输入不能读取。输出固定保留 `visual_quality_verified=false`。

半速可用播放器倍率审查同一最终文件；另生成半速衍生 MP4 时，在证据里记录衍生哈希与母版关系，`output_sha256` 仍关联当前母版。

**校验器不解码媒体，也不验证眼神、表情美术质量、烟雾的实际 alpha、图层真实像素或是否真的有人观看。** 它不会替作者写播放记录。独立审查、像素/alpha 预检、解码帧数/PTS/音轨检查仍由项目的渲染/验收工具承担。不能把填写的布尔值视为已执行验收。

## 本片互救案例如何落地

实际区间 `[1631,1708)` 共 77 帧，实际源 24fps：低落 → 汉娜忧虑抬眼 → 雪莉回应 → 四张各六帧的爆炸 → 无笑容确认 → 释然微笑。第三张烟雾覆盖换装差异时切正常形态；效果在完整画布绘制，艾玛身体与尾巴、歌词仍按约定层序处理。按实际源相位写 cel schedule；不要把每个状态一律分成 A/B 六帧。

本案例的真实交付信息存于本地 `research/manosaba-pair-r3/full-film-integration.json`。公开技能不带角色图、原片、绝对用户路径或这些私有证据。
